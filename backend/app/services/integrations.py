import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import settings
from app.integration_schemas import KycStartIn, PaymentIntentCreateIn, UploadInitIn
from app.models import (
    KycApplication,
    LedgerAccount,
    LedgerEntry,
    LedgerJournal,
    PaymentIntent,
    PaymentWebhookEvent,
    RefundRequest,
    StoredObject,
    UploadSession,
    User,
)
from app.providers import integration_descriptors, kyc_provider, payment_provider, storage_provider
from app.providers.contracts import (
    KycRequest,
    PaymentNotification,
    PaymentRequest,
    ProviderUnavailable,
    UploadRequest,
)
from app.security import ApiError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _money(value: Decimal) -> str:
    return format(value, "f")


def _number(prefix: str) -> str:
    return f"{prefix}{_now():%Y%m%d}{uuid4().hex[:12].upper()}"


def _configured(descriptor, code: str, message: str) -> None:
    if not descriptor.configured:
        raise ApiError(code, message, 503)


def provider_status() -> dict[str, dict]:
    return integration_descriptors()


def _account_balance(db: Session, account: LedgerAccount) -> Decimal:
    entries = db.query(LedgerEntry).filter(LedgerEntry.account_id == account.id).all()
    balance = Decimal("0")
    for entry in entries:
        balance += entry.amount if entry.direction == account.normal_side else -entry.amount
    return balance


def wallet_snapshot(db: Session, user: User) -> dict:
    accounts = db.query(LedgerAccount).filter(
        LedgerAccount.owner_user_id == user.id,
        LedgerAccount.status != "closed",
    ).all()
    balances: dict[str, dict[str, Decimal]] = {}
    for account in accounts:
        currency = balances.setdefault(
            account.currency,
            {"available": Decimal("0"), "frozen": Decimal("0")},
        )
        if account.account_type == "user_available":
            currency["available"] += _account_balance(db, account)
        elif account.account_type == "user_frozen":
            currency["frozen"] += _account_balance(db, account)

    if not balances:
        balances["CNY"] = {"available": Decimal("0"), "frozen": Decimal("0")}

    intents = db.query(PaymentIntent).filter(PaymentIntent.user_id == user.id).order_by(
        PaymentIntent.created_at.desc(), PaymentIntent.id.desc()
    ).limit(20).all()
    return {
        "provider": payment_provider().descriptor.as_dict(),
        "balances": [
            {
                "currency": currency,
                "available": _money(values["available"]),
                "frozen": _money(values["frozen"]),
            }
            for currency, values in sorted(balances.items())
        ],
        "payment_intents": [payment_intent_out(row) for row in intents],
        "ledger_mode": "double_entry",
    }


def payment_intent_out(row: PaymentIntent) -> dict:
    return {
        "id": row.id,
        "payment_no": row.payment_no,
        "order_id": row.order_id,
        "purpose": row.purpose,
        "amount": _money(row.amount),
        "currency": row.currency,
        "status": row.status,
        "provider": row.provider,
        "checkout_url": row.checkout_url,
        "expires_at": row.expires_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "version": row.version,
    }


def _payment_request(row: PaymentIntent) -> PaymentRequest:
    metadata = row.metadata_payload or {}
    return_path = str(metadata.get("return_path") or "/account/wallet")
    return PaymentRequest(
        payment_no=row.payment_no,
        user_id=row.user_id,
        amount=row.amount,
        currency=row.currency,
        purpose=row.purpose,
        return_url=f"{settings.FRONTEND_BASE_URL.rstrip('/')}{return_path}",
        idempotency_key=row.idempotency_key,
        client_ip=str(metadata.get("client_ip") or "127.0.0.1"),
        channel=str(metadata.get("payment_channel") or "") or None,
    )


def payment_checkout_payload(db: Session, user: User, payment_no: str) -> dict:
    row = db.query(PaymentIntent).filter(PaymentIntent.payment_no == payment_no).first()
    if row is None:
        raise ApiError("PAYMENT_NOT_FOUND", "支付单不存在", 404)
    if row.user_id != user.id:
        raise ApiError("PAYMENT_NOT_FOUND", "支付单不存在", 404)
    if row.status == "succeeded":
        raise ApiError("PAYMENT_ALREADY_SUCCEEDED", "支付已经完成", 409)
    if row.status != "provider_pending":
        raise ApiError("PAYMENT_NOT_PAYABLE", "支付单当前不能继续付款", 409)
    provider = payment_provider()
    if row.provider != provider.descriptor.provider or not provider.descriptor.configured:
        raise ApiError("PAYMENT_PROVIDER_UNAVAILABLE", "支付服务暂时不可用", 503)
    metadata = dict(row.metadata_payload or {})
    charge = metadata.get("provider_payload")
    if not isinstance(charge, dict) or charge.get("id") != row.provider_reference:
        raise ApiError("PAYMENT_CREDENTIAL_MISSING", "支付凭据不存在或已经失效", 409)
    return {
        "payment_no": row.payment_no,
        "provider": row.provider,
        "status": row.status,
        "channel": charge.get("channel"),
        "livemode": bool(charge.get("livemode")),
        "charge": charge,
        "return_url": _payment_request(row).return_url,
        "expires_at": row.expires_at,
    }


def create_payment_intent(
    db: Session,
    user: User,
    data: PaymentIntentCreateIn,
    *,
    idempotency_key: str,
    client_ip: str = "127.0.0.1",
) -> PaymentIntent:
    if data.purpose != "wallet_recharge":
        raise ApiError("PAYMENT_PURPOSE_UNSUPPORTED", "此支付入口当前只用于钱包充值", 422)
    existing = db.query(PaymentIntent).filter(
        PaymentIntent.idempotency_key == idempotency_key,
        PaymentIntent.user_id == user.id,
    ).first()
    if existing is not None:
        return existing

    provider = payment_provider()
    _configured(provider.descriptor, "PAYMENT_NOT_CONFIGURED", "支付服务尚未配置")
    payment_no = _number("PI")
    row = PaymentIntent(
        payment_no=payment_no,
        user_id=user.id,
        order_id=data.order_id,
        purpose=data.purpose,
        amount=data.amount,
        currency=data.currency,
        status="created",
        provider=provider.descriptor.provider,
        idempotency_key=idempotency_key,
        metadata_payload={
            "return_path": data.return_path,
            "client_ip": client_ip,
            "payment_channel": data.payment_channel,
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    try:
        session = provider.create_checkout(PaymentRequest(
            payment_no=payment_no,
            user_id=user.id,
            amount=data.amount,
            currency=data.currency,
            purpose=data.purpose,
            return_url=f"{settings.FRONTEND_BASE_URL.rstrip('/')}{data.return_path}",
            idempotency_key=idempotency_key,
            client_ip=client_ip,
            channel=data.payment_channel,
        ))
    except ProviderUnavailable as exc:
        row.status = "failed"
        row.failure_code = exc.reason
        row.failure_message = "支付服务暂时不可用"
        row.version += 1
        db.commit()
        raise ApiError("PAYMENT_PROVIDER_UNAVAILABLE", "支付服务暂时不可用", 503) from exc
    row.provider_reference = session.provider_reference
    row.checkout_url = session.checkout_url
    row.expires_at = session.expires_at
    metadata = dict(row.metadata_payload or {})
    metadata["provider_payload"] = dict(session.client_payload)
    row.metadata_payload = metadata
    row.status = "provider_pending"
    row.version += 1
    db.commit()
    db.refresh(row)
    return row


def _ledger_account(
    db: Session,
    *,
    code: str,
    owner_user_id: int | None,
    account_type: str,
    currency: str,
    normal_side: str,
) -> LedgerAccount:
    row = db.query(LedgerAccount).filter(LedgerAccount.account_code == code).first()
    if row is None:
        row = LedgerAccount(
            account_code=code,
            owner_user_id=owner_user_id,
            account_type=account_type,
            currency=currency,
            normal_side=normal_side,
            status="active",
        )
        db.add(row)
        db.flush()
    return row


def _safe_webhook_payload(payload: dict) -> dict:
    obj = payload.get("data", {}).get("object", {})
    safe_object = {
        key: obj.get(key)
        for key in (
            "id", "object", "order_no", "charge", "amount", "currency", "paid",
            "refunded", "status", "succeed", "livemode", "time_paid", "time_succeed",
        )
        if key in obj
    }
    return {
        "id": payload.get("id"),
        "type": payload.get("type"),
        "created": payload.get("created"),
        "livemode": payload.get("livemode"),
        "data": {"object": safe_object},
    }


def _process_pingxx_notification(
    db: Session,
    notification: PaymentNotification,
    payload: dict,
    payload_hash: str,
) -> bool:
    intent = db.query(PaymentIntent).filter(
        PaymentIntent.payment_no == notification.payment_no
    ).with_for_update().first()
    if intent is None or intent.provider != "pingxx":
        raise ApiError("PAYMENT_NOT_FOUND", "支付单不存在", 404)
    if intent.currency != notification.currency or intent.amount != notification.amount:
        raise ApiError("PAYMENT_AMOUNT_MISMATCH", "支付金额与订单不一致", 409)
    existing = db.query(PaymentWebhookEvent).filter(
        PaymentWebhookEvent.provider == "pingxx",
        PaymentWebhookEvent.event_key == notification.event_id,
    ).first()
    if existing is not None and existing.status == "processed":
        return True

    event = existing or PaymentWebhookEvent(
        provider="pingxx",
        event_key=notification.event_id,
        payment_intent_id=intent.id,
        provider_reference=notification.provider_reference,
        status="received",
        payload_hash=payload_hash,
        payload=_safe_webhook_payload(payload),
    )
    if existing is None:
        db.add(event)
        db.flush()

    if notification.event_type == "refund.succeeded":
        from app.services.server_rentals import complete_refund

        refund = db.query(RefundRequest).filter(
            RefundRequest.payment_intent_id == intent.id,
        ).with_for_update().first()
        if refund is None or refund.status not in {"processing", "completed"}:
            event.status = "rejected"
            event.failure_reason = "refund_not_processing"
            db.commit()
            raise ApiError("REFUND_STATE_INVALID", "退款单状态与 Ping++ 通知不一致", 409)
        if refund.amount != notification.amount or refund.currency != notification.currency:
            event.status = "rejected"
            event.failure_reason = "refund_amount_mismatch"
            db.commit()
            raise ApiError("PAYMENT_AMOUNT_MISMATCH", "退款金额与退款单不一致", 409)
        if refund.status != "completed":
            if refund.provider_reference != notification.refund_reference:
                event.status = "rejected"
                event.failure_reason = "refund_reference_mismatch"
                db.commit()
                raise ApiError("REFUND_REFERENCE_MISMATCH", "退款流水与退款单不一致", 409)
            complete_refund(
                db,
                None,
                refund.id,
                version=refund.version,
                provider_reference=notification.refund_reference or "",
                note="Ping++ refund.succeeded 回调已验签",
            )
        event.status = "processed"
        event.processed_at = _now()
        db.commit()
        return existing is not None

    if intent.status == "succeeded":
        event.status = "processed"
        event.processed_at = _now()
        db.commit()
        return True
    if intent.status != "provider_pending":
        event.status = "rejected"
        event.failure_reason = f"intent_status:{intent.status}"
        db.commit()
        raise ApiError("PAYMENT_STATE_INVALID", "支付单状态不允许入账", 409)
    if intent.purpose == "wallet_recharge":
        credit_owner_id = intent.user_id
        ledger_event_type = "wallet_recharge_succeeded"
    elif intent.purpose in {"server_rental", "lease_renewal"}:
        from app.services.server_rentals import apply_paid_intent

        credit_owner_id = apply_paid_intent(db, intent)
        ledger_event_type = (
            "server_rental_payment_succeeded"
            if intent.purpose == "server_rental"
            else "lease_renewal_payment_succeeded"
        )
    else:
        event.status = "failed"
        event.failure_reason = f"unsupported_purpose:{intent.purpose}"
        db.commit()
        raise ApiError("PAYMENT_PURPOSE_UNSUPPORTED", "支付业务尚未配置履约处理", 409)

    provider_clearing = _ledger_account(
        db,
        code=f"pingxx-provider-clearing-{intent.currency}",
        owner_user_id=None,
        account_type="provider_clearing",
        currency=intent.currency,
        normal_side="debit",
    )
    is_rental_payment = intent.purpose in {"server_rental", "lease_renewal"}
    settlement_account = _ledger_account(
        db,
        code=(
            f"user-{credit_owner_id}-frozen-{intent.currency}"
            if is_rental_payment
            else f"user-{credit_owner_id}-available-{intent.currency}"
        ),
        owner_user_id=credit_owner_id,
        account_type="user_frozen" if is_rental_payment else "user_available",
        currency=intent.currency,
        normal_side="credit",
    )
    post_balanced_journal(
        db,
        event_type=ledger_event_type,
        reference_type="payment_intent",
        reference_id=str(intent.id),
        currency=intent.currency,
        idempotency_key=f"pingxx:{notification.event_id}",
        entries=[
            (provider_clearing, "debit", intent.amount),
            (settlement_account, "credit", intent.amount),
        ],
        metadata={
            "payment_no": intent.payment_no,
            "provider_reference": notification.provider_reference,
        },
    )
    intent.status = "succeeded"
    intent.provider_reference = notification.provider_reference
    intent.failure_code = None
    intent.failure_message = None
    if is_rental_payment:
        metadata = dict(intent.metadata_payload or {})
        metadata["funds_state"] = "frozen"
        metadata["funds_frozen_at"] = _now().isoformat()
        intent.metadata_payload = metadata
    intent.version += 1
    if is_rental_payment:
        from app.services.server_rentals import finalize_paid_intent

        finalize_paid_intent(db, intent)
    event.status = "processed"
    event.processed_at = _now()
    db.commit()
    return False


def process_pingxx_webhook(db: Session, raw_body: bytes, signature: str) -> bool:
    provider = payment_provider()
    if provider.descriptor.provider != "pingxx" or not provider.descriptor.configured:
        raise ApiError("PAYMENT_PROVIDER_UNAVAILABLE", "支付服务暂时不可用", 503)
    try:
        notification = provider.verify_notification(raw_body, signature)
    except ProviderUnavailable as exc:
        raise ApiError("PAYMENT_VERIFICATION_UNAVAILABLE", "暂时无法核验支付结果", 502) from exc
    except ValueError as exc:
        raise ApiError("PAYMENT_NOTIFICATION_INVALID", "支付通知验签或状态校验失败", 400) from exc

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ApiError("PAYMENT_NOTIFICATION_INVALID", "支付通知格式不正确", 400) from exc
    return _process_pingxx_notification(
        db,
        notification,
        payload,
        hashlib.sha256(raw_body).hexdigest(),
    )


def reconcile_pingxx_payment(db: Session, user: User, payment_no: str) -> dict:
    """Recover a paid intent when a Ping++ webhook is delayed or missed."""
    intent = db.query(PaymentIntent).filter(
        PaymentIntent.payment_no == payment_no,
        PaymentIntent.user_id == user.id,
    ).first()
    if intent is None or intent.provider != "pingxx":
        raise ApiError("PAYMENT_NOT_FOUND", "支付单不存在", 404)
    if intent.status == "succeeded":
        return {"payment": payment_intent_out(intent), "reconciled": False}
    if intent.status != "provider_pending" or not intent.provider_reference:
        raise ApiError("PAYMENT_STATE_INVALID", "支付单状态不能进行补偿查询", 409)

    provider = payment_provider()
    if provider.descriptor.provider != "pingxx" or not provider.descriptor.configured:
        raise ApiError("PAYMENT_PROVIDER_UNAVAILABLE", "支付服务暂时不可用", 503)
    try:
        notification = provider.query_payment(intent.provider_reference)
    except ProviderUnavailable as exc:
        raise ApiError("PAYMENT_VERIFICATION_UNAVAILABLE", "暂时无法查询支付结果", 502) from exc
    except ValueError as exc:
        raise ApiError("PAYMENT_NOTIFICATION_INVALID", "支付平台返回的订单状态无效", 502) from exc
    if notification.payment_no != intent.payment_no:
        raise ApiError("PAYMENT_REFERENCE_MISMATCH", "支付平台订单号与本地订单不一致", 409)
    if not notification.succeeded:
        return {"payment": payment_intent_out(intent), "reconciled": False}

    payload = {
        "id": notification.event_id,
        "type": notification.event_type,
        "created": int(_now().timestamp()),
        "livemode": bool(settings.PINGXX_LIVE_MODE),
        "source": "provider_query",
        "data": {"object": {
            "id": notification.provider_reference,
            "object": "charge",
            "order_no": notification.payment_no,
            "amount": int(notification.amount * 100),
            "currency": notification.currency.lower(),
            "paid": True,
            "livemode": bool(settings.PINGXX_LIVE_MODE),
        }},
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    _process_pingxx_notification(
        db,
        notification,
        payload,
        hashlib.sha256(canonical).hexdigest(),
    )
    refreshed = db.query(PaymentIntent).filter(PaymentIntent.id == intent.id).one()
    return {"payment": payment_intent_out(refreshed), "reconciled": True}


def kyc_snapshot(db: Session, user: User) -> dict:
    row = db.query(KycApplication).filter(KycApplication.user_id == user.id).first()
    provider = kyc_provider().descriptor.as_dict()
    if row is None:
        return {"status": "unverified", "application": None, "provider": provider}
    return {
        "status": row.status,
        "application": {
            "id": row.id,
            "status": row.status,
            "verification_type": row.verification_type,
            "country_code": row.country_code,
            "provider": row.provider,
            "review_note": row.review_note,
            "submitted_at": row.submitted_at,
            "reviewed_at": row.reviewed_at,
            "expires_at": row.expires_at,
            "updated_at": row.updated_at,
            "version": row.version,
        },
        "provider": provider,
    }


def start_kyc(db: Session, user: User, data: KycStartIn) -> tuple[KycApplication, str]:
    provider = kyc_provider()
    _configured(provider.descriptor, "KYC_NOT_CONFIGURED", "实名认证服务尚未配置")
    row = db.query(KycApplication).filter(KycApplication.user_id == user.id).with_for_update().first()
    if row is not None and row.status in ("pending", "approved"):
        raise ApiError("KYC_ALREADY_ACTIVE", "当前实名认证状态不能重新发起", 409)
    if row is None:
        row = KycApplication(
            user_id=user.id,
            provider=provider.descriptor.provider,
            verification_type=data.verification_type,
            country_code=data.country_code,
            status="draft",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    else:
        row.provider = provider.descriptor.provider
        row.verification_type = data.verification_type
        row.country_code = data.country_code
        row.status = "draft"
        row.review_note = None
        row.version += 1
        db.commit()
        db.refresh(row)
    try:
        session = provider.start_verification(KycRequest(
            application_id=row.id,
            user_id=user.id,
            verification_type=row.verification_type,
            country_code=row.country_code,
            return_url=f"{settings.FRONTEND_BASE_URL.rstrip('/')}{data.return_path}",
        ))
    except ProviderUnavailable as exc:
        raise ApiError("KYC_PROVIDER_UNAVAILABLE", "实名认证服务暂时不可用", 503) from exc
    row.provider_reference = session.provider_reference
    row.submitted_at = _now()
    row.expires_at = session.expires_at
    row.status = "pending"
    row.version += 1
    db.commit()
    db.refresh(row)
    return row, session.verification_url


def file_snapshot(db: Session, user: User) -> dict:
    rows = db.query(StoredObject).filter(
        StoredObject.owner_user_id == user.id,
        StoredObject.status != "deleted",
    ).order_by(StoredObject.created_at.desc(), StoredObject.id.desc()).limit(50).all()
    return {
        "provider": storage_provider().descriptor.as_dict(),
        "max_upload_bytes": settings.PRIVATE_UPLOAD_MAX_BYTES,
        "objects": [stored_object_out(row) for row in rows],
    }


def stored_object_out(row: StoredObject) -> dict:
    return {
        "id": row.id,
        "object_no": row.object_no,
        "category": row.category,
        "filename": row.original_filename,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
        "status": row.status,
        "is_private": row.is_private,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def init_upload(db: Session, user: User, data: UploadInitIn) -> tuple[StoredObject, UploadSession, object]:
    provider = storage_provider()
    _configured(provider.descriptor, "OBJECT_STORAGE_NOT_CONFIGURED", "私有对象存储尚未配置")
    if data.size_bytes > settings.PRIVATE_UPLOAD_MAX_BYTES:
        raise ApiError("FILE_TOO_LARGE", "文件超过当前允许的大小", 413)
    application = None
    if data.kyc_application_id is not None:
        application = db.query(KycApplication).filter(
            KycApplication.id == data.kyc_application_id,
            KycApplication.user_id == user.id,
        ).first()
        if application is None:
            raise ApiError("KYC_APPLICATION_NOT_FOUND", "实名认证申请不存在", 404)
    upload_id = uuid4().hex
    object_no = _number("SO")
    row = StoredObject(
        object_no=object_no,
        owner_user_id=user.id,
        kyc_application_id=application.id if application else None,
        category=data.category,
        provider=provider.descriptor.provider,
        original_filename=data.filename,
        mime_type=data.mime_type,
        size_bytes=data.size_bytes,
        checksum_sha256=data.checksum_sha256.casefold() if data.checksum_sha256 else None,
        status="initiating",
        is_private=True,
    )
    db.add(row)
    db.flush()
    upload = UploadSession(
        id=upload_id,
        stored_object_id=row.id,
        status="pending",
        expires_at=_now() + timedelta(minutes=settings.PRIVATE_UPLOAD_TTL_MINUTES),
    )
    db.add(upload)
    db.commit()
    db.refresh(row)
    try:
        target = provider.create_upload(UploadRequest(
            upload_id=upload_id,
            object_no=object_no,
            user_id=user.id,
            category=data.category,
            filename=data.filename,
            mime_type=data.mime_type,
            size_bytes=data.size_bytes,
            checksum_sha256=data.checksum_sha256,
        ))
    except ProviderUnavailable as exc:
        row.status = "failed"
        upload.status = "failed"
        db.commit()
        raise ApiError("OBJECT_STORAGE_UNAVAILABLE", "私有对象存储暂时不可用", 503) from exc
    row.bucket = target.bucket
    row.object_key = target.object_key
    row.status = "uploading"
    upload.provider_reference = target.provider_reference
    upload.status = "uploading"
    if target.expires_at:
        upload.expires_at = target.expires_at
    db.commit()
    db.refresh(row)
    db.refresh(upload)
    return row, upload, target


def complete_upload(db: Session, user: User, upload_id: str, etag: str | None) -> StoredObject:
    provider = storage_provider()
    _configured(provider.descriptor, "OBJECT_STORAGE_NOT_CONFIGURED", "私有对象存储尚未配置")
    result = db.query(UploadSession, StoredObject).join(
        StoredObject, StoredObject.id == UploadSession.stored_object_id
    ).filter(
        UploadSession.id == upload_id,
        StoredObject.owner_user_id == user.id,
    ).first()
    if result is None:
        raise ApiError("UPLOAD_NOT_FOUND", "上传会话不存在", 404)
    upload, row = result
    if upload.status == "completed":
        return row
    if upload.status != "uploading" or upload.expires_at <= _now():
        raise ApiError("UPLOAD_NOT_COMPLETABLE", "上传会话已失效", 409)
    try:
        provider.complete_upload(upload.provider_reference or "", row.object_key or "", etag)
    except ProviderUnavailable as exc:
        raise ApiError("OBJECT_STORAGE_UNAVAILABLE", "私有对象存储暂时不可用", 503) from exc
    upload.status = "completed"
    row.status = "available"
    db.commit()
    db.refresh(row)
    return row


def post_balanced_journal(
    db: Session,
    *,
    event_type: str,
    reference_type: str,
    reference_id: str,
    currency: str,
    idempotency_key: str,
    entries: list[tuple[LedgerAccount, str, Decimal]],
    metadata: dict | None = None,
) -> LedgerJournal:
    existing = db.query(LedgerJournal).filter(
        LedgerJournal.idempotency_key == idempotency_key
    ).first()
    if existing is not None:
        return existing
    debits = sum((amount for _, direction, amount in entries if direction == "debit"), Decimal("0"))
    credits = sum((amount for _, direction, amount in entries if direction == "credit"), Decimal("0"))
    if not entries or debits <= 0 or debits != credits:
        raise ApiError("LEDGER_NOT_BALANCED", "账本借贷不平衡", 409)
    for account, direction, amount in entries:
        if direction not in ("debit", "credit") or amount <= 0 or account.currency != currency:
            raise ApiError("LEDGER_ENTRY_INVALID", "账本分录不符合要求", 409)
    journal = LedgerJournal(
        journal_no=_number("LJ"),
        event_type=event_type,
        reference_type=reference_type,
        reference_id=reference_id,
        currency=currency,
        idempotency_key=idempotency_key,
        status="posted",
        metadata_payload=metadata or {},
    )
    db.add(journal)
    db.flush()
    for account, direction, amount in entries:
        db.add(LedgerEntry(
            journal_id=journal.id,
            account_id=account.id,
            direction=direction,
            amount=amount,
        ))
    db.commit()
    db.refresh(journal)
    return journal
