import base64
import binascii
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from urllib.parse import urlparse

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AccessLease,
    AgentCommand,
    BuyerSshKey,
    DisputeCase,
    InventoryReservation,
    LedgerAccount,
    LedgerEntry,
    LedgerJournal,
    MerchantServer,
    Order,
    OrderEvent,
    PaymentIntent,
    Product,
    RefundRequest,
    SupplierApplication,
    User,
)
from app.config import settings
from app.providers import payment_provider
from app.providers.contracts import PaymentRequest, ProviderUnavailable
from app.security import ApiError, ensure_verified_email
from app.server_rental_schemas import DirectServerRentalIn, LeaseRenewIn, SshKeyCreateIn, SshKeyUpdateIn
from app.services import resources as resource_service
from app.services.internal_modules import create_notification


SUPPORTED_SSH_ALGORITHMS = {
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
}
RENEWAL_GRACE = timedelta(hours=2)
logger = logging.getLogger("app.server_rentals")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _number(prefix: str) -> str:
    return f"{prefix}{_now():%Y%m%d}{uuid4().hex[:12].upper()}"


def _commit(db: Session, code: str = "SERVER_RENTAL_CONFLICT") -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.exception("server rental transaction conflict", extra={"event": code})
        raise ApiError(code, "服务器租赁数据发生冲突，请刷新后重试", 409) from exc


def _parse_public_key(value: str) -> tuple[str, str, str]:
    text = " ".join(value.strip().split())
    if "PRIVATE KEY" in text.upper():
        raise ApiError("SSH_PRIVATE_KEY_FORBIDDEN", "只能提交 SSH 公钥，禁止上传私钥", 422)
    parts = text.split(" ", 2)
    if len(parts) < 2 or parts[0] not in SUPPORTED_SSH_ALGORITHMS:
        raise ApiError("SSH_PUBLIC_KEY_INVALID", "请输入有效的 OpenSSH 公钥", 422)
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ApiError("SSH_PUBLIC_KEY_INVALID", "SSH 公钥编码无效", 422) from exc
    if len(blob) < 16:
        raise ApiError("SSH_PUBLIC_KEY_INVALID", "SSH 公钥内容不完整", 422)
    algorithm_length = int.from_bytes(blob[:4], "big")
    try:
        embedded_algorithm = blob[4:4 + algorithm_length].decode("ascii")
    except UnicodeDecodeError as exc:
        raise ApiError("SSH_PUBLIC_KEY_INVALID", "SSH 公钥算法标识无效", 422) from exc
    if embedded_algorithm != parts[0]:
        raise ApiError("SSH_PUBLIC_KEY_INVALID", "SSH 公钥算法与编码内容不一致", 422)
    fingerprint = base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    normalized = f"{parts[0]} {parts[1]}" + (f" {parts[2]}" if len(parts) == 3 else "")
    return parts[0], f"SHA256:{fingerprint}", normalized


def ssh_key_out(row: BuyerSshKey) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "algorithm": row.algorithm,
        "fingerprint": row.fingerprint_sha256,
        "public_key_preview": f"{row.algorithm} …{row.public_key.split()[1][-12:]}",
        "status": row.status,
        "last_used_at": row.last_used_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "version": row.version,
    }


def list_ssh_keys(db: Session, user: User) -> list[BuyerSshKey]:
    return db.query(BuyerSshKey).filter(BuyerSshKey.user_id == user.id).order_by(
        BuyerSshKey.status.asc(), BuyerSshKey.created_at.desc()
    ).all()


def create_ssh_key(db: Session, user: User, data: SshKeyCreateIn) -> BuyerSshKey:
    if user.role != "personal":
        raise ApiError("BUYER_REQUIRED", "只有买家账号可以添加服务器登录公钥", 403)
    algorithm, fingerprint, public_key = _parse_public_key(data.public_key)
    existing = db.query(BuyerSshKey).filter(
        BuyerSshKey.user_id == user.id,
        BuyerSshKey.fingerprint_sha256 == fingerprint,
    ).first()
    if existing is not None:
        raise ApiError("SSH_KEY_ALREADY_EXISTS", "这个 SSH 公钥已经添加", 409)
    row = BuyerSshKey(
        user_id=user.id,
        name=data.name.strip(),
        algorithm=algorithm,
        fingerprint_sha256=fingerprint,
        public_key=public_key,
        status="active",
        version=1,
    )
    db.add(row)
    _commit(db, "SSH_KEY_CONFLICT")
    db.refresh(row)
    return row


def update_ssh_key(db: Session, user: User, key_id: int, data: SshKeyUpdateIn) -> BuyerSshKey:
    row = db.query(BuyerSshKey).filter(
        BuyerSshKey.id == key_id, BuyerSshKey.user_id == user.id
    ).with_for_update().first()
    if row is None:
        raise ApiError("SSH_KEY_NOT_FOUND", "SSH 公钥不存在", 404)
    if row.version != data.version:
        raise ApiError("SSH_KEY_VERSION_CONFLICT", "公钥记录已更新，请刷新后重试", 409)
    if row.status != "active":
        raise ApiError("SSH_KEY_REVOKED", "已撤销的公钥不能修改", 409)
    row.name = data.name.strip()
    row.version += 1
    _commit(db, "SSH_KEY_CONFLICT")
    db.refresh(row)
    return row


def revoke_ssh_key(db: Session, user: User, key_id: int, version: int) -> BuyerSshKey:
    row = db.query(BuyerSshKey).filter(
        BuyerSshKey.id == key_id, BuyerSshKey.user_id == user.id
    ).with_for_update().first()
    if row is None:
        raise ApiError("SSH_KEY_NOT_FOUND", "SSH 公钥不存在", 404)
    if row.version != version:
        raise ApiError("SSH_KEY_VERSION_CONFLICT", "公钥记录已更新，请刷新后重试", 409)
    in_use = db.query(AccessLease.id).filter(
        AccessLease.ssh_key_id == row.id,
        AccessLease.status.in_(("pending_authorization", "active", "grace")),
    ).first()
    if in_use:
        raise ApiError("SSH_KEY_IN_USE", "公钥仍被有效租约使用，租约结束后才能撤销", 409)
    if row.status != "revoked":
        row.status = "revoked"
        row.revoked_at = _now()
        row.version += 1
        _commit(db, "SSH_KEY_CONFLICT")
        db.refresh(row)
    return row


def _account(
    db: Session, *, code: str, owner_user_id: int | None, account_type: str,
    currency: str, normal_side: str,
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


def _post_journal(
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
    debits = sum((amount for _, side, amount in entries if side == "debit"), Decimal("0"))
    credits = sum((amount for _, side, amount in entries if side == "credit"), Decimal("0"))
    if not entries or debits <= 0 or debits != credits:
        raise ApiError("LEDGER_NOT_BALANCED", "账本借贷不平衡", 409)
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
    for account, side, amount in entries:
        if side not in ("debit", "credit") or amount <= 0 or account.currency != currency:
            raise ApiError("LEDGER_ENTRY_INVALID", "账本分录不符合要求", 409)
        db.add(LedgerEntry(
            journal_id=journal.id,
            account_id=account.id,
            direction=side,
            amount=amount,
        ))
    return journal


def _intent_for_lease(db: Session, lease: AccessLease) -> PaymentIntent | None:
    return db.query(PaymentIntent).filter(
        PaymentIntent.order_id == lease.order_id,
        PaymentIntent.purpose.in_(("server_rental", "lease_renewal")),
        PaymentIntent.status.in_(("succeeded", "refund_pending")),
    ).order_by(PaymentIntent.created_at.desc(), PaymentIntent.id.desc()).first()


def release_frozen_payment(
    db: Session, intent: PaymentIntent, *, now: datetime | None = None
) -> bool:
    """Settle a matured rental payment after the T+1 hold and dispute check."""
    metadata = dict(intent.metadata_payload or {})
    if metadata.get("funds_state") != "frozen":
        return False
    order = db.get(Order, intent.order_id)
    if order is None:
        raise ApiError("PAYMENT_ORDER_NOT_FOUND", "支付关联订单不存在", 409)
    lease = db.query(AccessLease).filter(AccessLease.order_id == order.id).first()
    if lease is None or lease.expires_at is None:
        return False
    current = now or _now()
    eligible_at = _aware(lease.expires_at) + timedelta(hours=settings.SETTLEMENT_HOLD_HOURS)
    if current < eligible_at:
        return False
    active_dispute = db.query(DisputeCase.id).filter(
        DisputeCase.order_id == order.id,
        DisputeCase.status.in_(("open", "under_review")),
    ).first()
    if active_dispute is not None:
        return False
    frozen = _account(
        db,
        code=f"user-{order.supplier_id}-frozen-{intent.currency}",
        owner_user_id=order.supplier_id,
        account_type="user_frozen",
        currency=intent.currency,
        normal_side="credit",
    )
    available = _account(
        db,
        code=f"user-{order.supplier_id}-available-{intent.currency}",
        owner_user_id=order.supplier_id,
        account_type="user_available",
        currency=intent.currency,
        normal_side="credit",
    )
    platform_revenue = _account(
        db,
        code=f"platform-commission-{intent.currency}",
        owner_user_id=None,
        account_type="platform_revenue",
        currency=intent.currency,
        normal_side="credit",
    )
    commission = (intent.amount * settings.PLATFORM_COMMISSION_RATE).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    supplier_amount = intent.amount - commission
    credits: list[tuple[LedgerAccount, str, Decimal]] = []
    if supplier_amount > 0:
        credits.append((available, "credit", supplier_amount))
    if commission > 0:
        credits.append((platform_revenue, "credit", commission))
    _post_journal(
        db,
        event_type="server_rental_funds_released",
        reference_type="payment_intent",
        reference_id=str(intent.id),
        currency=intent.currency,
        idempotency_key=f"rental-release:{intent.id}",
        entries=[
            (frozen, "debit", intent.amount),
            *credits,
        ],
        metadata={
            "payment_no": intent.payment_no,
            "order_no": order.order_no,
            "gross_amount": format(intent.amount, "f"),
            "commission_rate": format(settings.PLATFORM_COMMISSION_RATE, "f"),
            "commission_amount": format(commission, "f"),
            "supplier_amount": format(supplier_amount, "f"),
            "settlement_eligible_at": eligible_at.isoformat(),
        },
    )
    metadata["funds_state"] = "released"
    metadata["funds_released_at"] = current.isoformat()
    metadata["gross_amount"] = format(intent.amount, "f")
    metadata["commission_rate"] = format(settings.PLATFORM_COMMISSION_RATE, "f")
    metadata["commission_amount"] = format(commission, "f")
    metadata["supplier_amount"] = format(supplier_amount, "f")
    metadata["settlement_eligible_at"] = eligible_at.isoformat()
    intent.metadata_payload = metadata
    intent.version += 1
    create_notification(
        db,
        user_id=order.supplier_id,
        category="payment",
        title="服务器租金已结算",
        body=(
            f"订单 {order.order_no} 已扣除 {format(settings.PLATFORM_COMMISSION_RATE * 100, 'f')}% "
            f"平台佣金，{intent.currency} {format(supplier_amount, 'f')} 已进入可提现余额。"
        ),
        action_path="/supplier/revenue",
    )
    return True


def request_compensation_refund(
    db: Session,
    intent: PaymentIntent,
    lease: AccessLease,
    *,
    reason_code: str,
    reason: str,
) -> RefundRequest:
    existing = db.query(RefundRequest).filter(
        RefundRequest.payment_intent_id == intent.id
    ).first()
    if existing is not None:
        return existing
    order = db.get(Order, intent.order_id)
    if order is None:
        raise ApiError("PAYMENT_ORDER_NOT_FOUND", "支付关联订单不存在", 409)
    metadata = dict(intent.metadata_payload or {})
    refund = RefundRequest(
        refund_no=_number("RF"),
        payment_intent_id=intent.id,
        order_id=order.id,
        buyer_id=order.buyer_id,
        supplier_id=order.supplier_id,
        amount=intent.amount,
        currency=intent.currency,
        provider=intent.provider,
        status="requested",
        reason_code=reason_code,
        reason=reason[:500],
        version=1,
    )
    db.add(refund)
    intent.status = "refund_pending"
    intent.failure_code = reason_code
    intent.failure_message = reason[:255]
    metadata["funds_state"] = "refund_pending"
    intent.metadata_payload = metadata
    intent.version += 1

    if intent.purpose == "server_rental":
        previous = order.status
        order.payment_status = "refund_pending"
        order.status = "cancelled"
        order.cancelled_at = _now()
        order.cancel_reason = "SSH 授权失败，等待原路退款"
        order.version += 1
        lease.status = "failed"
        lease.failure_reason = reason[:500]
        lease.version += 1
        resource_service.release_for_order(db, order.id, "SSH 授权失败，退款释放服务器")
        db.add(OrderEvent(
            order_id=order.id,
            actor_user_id=None,
            actor_role="system",
            event_type="delivery_failed_refund_requested",
            from_status=previous,
            to_status="cancelled",
            payload={"payment_no": intent.payment_no, "reason_code": reason_code},
        ))
    else:
        rollback = metadata.get("renewal_rollback") or {}
        if rollback:
            order.amount = Decimal(str(rollback.get("order_amount", order.amount)))
            order.duration_hours = int(rollback.get("duration_hours") or order.duration_hours or 1)
            expires_at = rollback.get("expires_at")
            grace_expires_at = rollback.get("grace_expires_at")
            lease.expires_at = datetime.fromisoformat(expires_at) if expires_at else lease.expires_at
            lease.grace_expires_at = (
                datetime.fromisoformat(grace_expires_at) if grace_expires_at else lease.grace_expires_at
            )
            lease.status = rollback.get("status") or "grace"
            order.version += 1
            lease.version += 1

    create_notification(
        db,
        user_id=order.buyer_id,
        category="order",
        title="服务器开通失败，已进入退款处理",
        body=f"订单 {order.order_no} 未能完成 SSH 授权，平台已生成退款单 {refund.refund_no}。",
        action_path="/account/orders",
    )
    create_notification(
        db,
        user_id=order.supplier_id,
        category="order",
        title="服务器授权失败，款项不会结算",
        body=f"订单 {order.order_no} 的冻结款项已进入退款处理，请检查 Agent 与 SSH 服务。",
        action_path="/supplier/leases",
    )
    return refund


def request_dispute_refunds(
    db: Session,
    dispute: DisputeCase,
    *,
    resolution: str,
) -> list[RefundRequest]:
    """Turn every still-frozen payment on an order into an auditable refund request."""
    order = db.get(Order, dispute.order_id)
    if order is None:
        raise ApiError("DISPUTE_ORDER_NOT_FOUND", "争议关联订单不存在", 409)
    lease = db.query(AccessLease).filter(AccessLease.order_id == order.id).first()
    intents = db.query(PaymentIntent).filter(
        PaymentIntent.order_id == order.id,
        PaymentIntent.purpose.in_(("server_rental", "lease_renewal")),
        PaymentIntent.status.in_(("succeeded", "refund_pending")),
    ).order_by(PaymentIntent.id).with_for_update().all()
    refunds: list[RefundRequest] = []
    for intent in intents:
        existing = db.query(RefundRequest).filter(
            RefundRequest.payment_intent_id == intent.id
        ).first()
        if existing is not None:
            refunds.append(existing)
            continue
        metadata = dict(intent.metadata_payload or {})
        if metadata.get("funds_state") != "frozen":
            raise ApiError(
                "DISPUTE_FUNDS_ALREADY_SETTLED",
                "订单资金已经结算，不能再自动生成退款",
                409,
            )
        refund = RefundRequest(
            refund_no=_number("RF"),
            payment_intent_id=intent.id,
            order_id=order.id,
            buyer_id=order.buyer_id,
            supplier_id=order.supplier_id,
            amount=intent.amount,
            currency=intent.currency,
            provider=intent.provider,
            status="requested",
            reason_code="DISPUTE_BUYER_WON",
            reason=f"争议 {dispute.dispute_no} 裁决买家胜诉：{resolution}"[:500],
            version=1,
        )
        db.add(refund)
        metadata.update({
            "funds_state": "refund_pending",
            "dispute_no": dispute.dispute_no,
            "refund_reason": "DISPUTE_BUYER_WON",
        })
        intent.status = "refund_pending"
        intent.failure_code = "DISPUTE_BUYER_WON"
        intent.failure_message = resolution[:255]
        intent.metadata_payload = metadata
        intent.version += 1
        refunds.append(refund)
    if not refunds:
        raise ApiError("DISPUTE_PAYMENT_NOT_FOUND", "争议订单没有可退款的付款记录", 409)

    now = _now()
    previous = order.status
    order.payment_status = "refund_pending"
    order.status = "cancelled"
    order.cancelled_at = now
    order.cancel_reason = f"争议 {dispute.dispute_no} 裁决买家胜诉，等待退款"
    order.version += 1
    if lease is not None and lease.status in ("pending_authorization", "active", "grace"):
        server = db.get(MerchantServer, lease.server_id)
        if server is not None:
            command = _agent_command(db, server, lease, "revoke_key", {
                "username": lease.ssh_username,
                "reason": "dispute_refund",
                "dispute_no": dispute.dispute_no,
            })
            if command.status == "succeeded":
                lease.access_revoked_at = now
        lease.status = "grace"
        lease.grace_expires_at = now + RENEWAL_GRACE
        lease.failure_reason = "争议裁决退款，SSH 权限已撤销"
        lease.version += 1
    db.add(OrderEvent(
        order_id=order.id,
        actor_user_id=dispute.resolved_by_user_id,
        actor_role="admin",
        event_type="dispute_refund_requested",
        from_status=previous,
        to_status="cancelled",
        payload={
            "dispute_no": dispute.dispute_no,
            "refund_nos": [row.refund_no for row in refunds],
        },
    ))
    create_notification(
        db,
        user_id=order.buyer_id,
        category="payment",
        title="争议裁决退款已创建",
        body=f"订单 {order.order_no} 已生成 {len(refunds)} 笔退款申请，等待平台完成原路退款。",
        action_path="/account/disputes",
    )
    create_notification(
        db,
        user_id=order.supplier_id,
        category="payment",
        title="争议订单进入退款处理",
        body=f"订单 {order.order_no} 的冻结款项不会结算，SSH 权限已进入撤销流程。",
        action_path="/supplier/leases",
    )
    return refunds


def finalize_paid_intent(db: Session, intent: PaymentIntent) -> None:
    lease = db.query(AccessLease).filter(AccessLease.order_id == intent.order_id).first()
    if lease is None:
        raise ApiError("PAYMENT_LEASE_NOT_FOUND", "支付关联租约不存在", 409)
    if lease.status == "active":
        release_frozen_payment(db, intent)
    elif lease.status == "failed":
        request_compensation_refund(
            db,
            intent,
            lease,
            reason_code="SSH_AUTHORIZATION_FAILED",
            reason=lease.failure_reason or "服务器 Agent 未能完成 SSH 公钥授权",
        )


def refund_out(row: RefundRequest, order: Order, intent: PaymentIntent) -> dict:
    return {
        "id": row.id,
        "refund_no": row.refund_no,
        "payment_no": intent.payment_no,
        "order_id": order.id,
        "order_no": order.order_no,
        "purpose": intent.purpose,
        "buyer_id": row.buyer_id,
        "supplier_id": row.supplier_id,
        "amount": format(row.amount, "f"),
        "currency": row.currency,
        "provider": row.provider,
        "status": row.status,
        "reason_code": row.reason_code,
        "reason": row.reason,
        "provider_reference": row.provider_reference,
        "admin_note": row.admin_note,
        "requested_at": row.requested_at,
        "processed_at": row.processed_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "version": row.version,
    }


def list_refunds(
    db: Session, *, status: str | None = None
) -> list[tuple[RefundRequest, Order, PaymentIntent]]:
    query = db.query(RefundRequest, Order, PaymentIntent).join(
        Order, Order.id == RefundRequest.order_id
    ).join(PaymentIntent, PaymentIntent.id == RefundRequest.payment_intent_id)
    if status:
        query = query.filter(RefundRequest.status == status)
    return query.order_by(RefundRequest.created_at.desc(), RefundRequest.id.desc()).all()


def initiate_refund(
    db: Session,
    admin: User,
    refund_id: int,
    *,
    version: int,
    note: str | None,
) -> RefundRequest:
    row = db.query(RefundRequest).filter(RefundRequest.id == refund_id).with_for_update().first()
    if row is None:
        raise ApiError("REFUND_NOT_FOUND", "退款工单不存在", 404)
    if row.version != version:
        raise ApiError("REFUND_VERSION_CONFLICT", "退款工单已更新，请刷新后重试", 409)
    if row.status != "requested":
        raise ApiError("REFUND_STATE_INVALID", "当前退款状态不能发起原路退款", 409)
    intent = db.get(PaymentIntent, row.payment_intent_id)
    if intent is None or not intent.provider_reference:
        raise ApiError("REFUND_DATA_INCOMPLETE", "退款关联支付流水不存在", 409)
    provider = payment_provider()
    if (
        row.provider != "pingxx"
        or provider.descriptor.provider != "pingxx"
        or not provider.descriptor.configured
    ):
        raise ApiError("PAYMENT_PROVIDER_UNAVAILABLE", "Ping++ 退款服务暂时不可用", 503)

    row.status = "processing"
    row.admin_note = note.strip() if note else "已向 Ping++ 发起原路退款"
    row.version += 1
    _commit(db, "REFUND_INITIATION_CONFLICT")
    db.refresh(row)
    try:
        session = provider.create_refund(
            provider_reference=intent.provider_reference,
            refund_no=row.refund_no,
            amount=row.amount,
            reason=row.reason,
        )
    except ProviderUnavailable as exc:
        row.admin_note = f"Ping++ 退款请求状态待确认：{exc.reason}"[:500]
        _commit(db, "REFUND_INITIATION_CONFLICT")
        raise ApiError(
            "REFUND_PROVIDER_UNCERTAIN",
            "Ping++ 退款请求结果暂时无法确认，请先在 Ping++ 后台核对，勿重复提交",
            502,
        ) from exc
    row.provider_reference = session.provider_reference
    row.admin_note = (
        f"{note.strip()} · " if note and note.strip() else ""
    ) + f"Ping++ 状态：{session.status}"
    row.version += 1
    db.add(OrderEvent(
        order_id=row.order_id,
        actor_user_id=admin.id,
        actor_role=admin.role,
        event_type="refund_initiated",
        from_status="refund_pending",
        to_status="refund_pending",
        payload={"refund_no": row.refund_no, "provider_reference": session.provider_reference},
    ))
    _commit(db, "REFUND_INITIATION_CONFLICT")
    db.refresh(row)
    return row


def complete_refund(
    db: Session,
    admin: User | None,
    refund_id: int,
    *,
    version: int,
    provider_reference: str,
    note: str | None,
) -> RefundRequest:
    row = db.query(RefundRequest).filter(RefundRequest.id == refund_id).with_for_update().first()
    if row is None:
        raise ApiError("REFUND_NOT_FOUND", "退款工单不存在", 404)
    if row.version != version:
        raise ApiError("REFUND_VERSION_CONFLICT", "退款工单已更新，请刷新后重试", 409)
    if row.status not in ("processing", "completed"):
        raise ApiError("REFUND_STATE_INVALID", "当前退款状态不能确认完成", 409)
    if row.status == "completed":
        return row
    intent = db.get(PaymentIntent, row.payment_intent_id)
    order = db.get(Order, row.order_id)
    if intent is None or order is None:
        raise ApiError("REFUND_DATA_INCOMPLETE", "退款关联数据不完整", 409)
    metadata = dict(intent.metadata_payload or {})
    if metadata.get("funds_state") == "refund_pending":
        frozen = _account(
            db,
            code=f"user-{order.supplier_id}-frozen-{row.currency}",
            owner_user_id=order.supplier_id,
            account_type="user_frozen",
            currency=row.currency,
            normal_side="credit",
        )
        provider = _account(
            db,
            code=f"{row.provider}-provider-clearing-{row.currency}",
            owner_user_id=None,
            account_type="provider_clearing",
            currency=row.currency,
            normal_side="debit",
        )
        _post_journal(
            db,
            event_type="server_rental_refund_completed",
            reference_type="refund_request",
            reference_id=str(row.id),
            currency=row.currency,
            idempotency_key=f"rental-refund:{row.id}",
            entries=[
                (frozen, "debit", row.amount),
                (provider, "credit", row.amount),
            ],
            metadata={
                "refund_no": row.refund_no,
                "payment_no": intent.payment_no,
                "provider_reference": provider_reference,
            },
        )
    now = _now()
    row.status = "completed"
    row.provider_reference = provider_reference.strip()
    row.admin_note = note.strip() if note else None
    row.processed_at = now
    row.version += 1
    intent.status = "refunded"
    intent.failure_code = None
    intent.failure_message = None
    metadata["funds_state"] = "refunded"
    metadata["refunded_at"] = now.isoformat()
    metadata["refund_provider_reference"] = provider_reference.strip()
    intent.metadata_payload = metadata
    intent.version += 1
    if intent.purpose == "server_rental":
        order.payment_status = "refunded"
        order.version += 1
    db.add(OrderEvent(
        order_id=order.id,
        actor_user_id=admin.id if admin else None,
        actor_role=admin.role if admin else "system",
        event_type="refund_completed",
        from_status=order.status,
        to_status=order.status,
        payload={"refund_no": row.refund_no, "provider_reference": provider_reference.strip()},
    ))
    create_notification(
        db,
        user_id=order.buyer_id,
        category="order",
        title="退款已完成",
        body=f"订单 {order.order_no} 的退款 {row.refund_no} 已处理完成。",
        action_path="/account/orders",
    )
    _commit(db, "REFUND_COMPLETION_CONFLICT")
    db.refresh(row)
    return row


def complete_local_refund(
    db: Session,
    admin: User,
    refund_id: int,
    *,
    version: int,
    provider_reference: str,
    note: str | None,
) -> RefundRequest:
    row = db.query(RefundRequest).filter(RefundRequest.id == refund_id).with_for_update().first()
    if row is None:
        raise ApiError("REFUND_NOT_FOUND", "退款工单不存在", 404)
    if row.provider != "local_placeholder":
        raise ApiError(
            "REFUND_PROVIDER_CONFIRMATION_REQUIRED",
            "Ping++ 退款只能由已验签的 refund.succeeded 回调确认完成",
            409,
        )
    if row.version != version:
        raise ApiError("REFUND_VERSION_CONFLICT", "退款工单已更新，请刷新后重试", 409)
    if row.status == "requested":
        row.status = "processing"
    return complete_refund(
        db,
        admin,
        refund_id,
        version=version,
        provider_reference=provider_reference,
        note=note,
    )


def _post_test_payment(
    db: Session,
    order: Order,
    *,
    idempotency_key: str,
    purpose: str,
    amount: Decimal | None = None,
) -> PaymentIntent:
    payment_amount = amount if amount is not None else order.amount
    now = _now()
    intent = PaymentIntent(
        payment_no=_number("PI"),
        user_id=order.buyer_id,
        order_id=order.id,
        purpose=purpose,
        amount=payment_amount,
        currency=order.currency,
        status="succeeded",
        provider="local_placeholder",
        provider_reference=f"placeholder:{order.order_no}",
        idempotency_key=idempotency_key,
        metadata_payload={
            "funds_state": "frozen",
            "funds_frozen_at": now.isoformat(),
            "settlement_hold_hours": settings.SETTLEMENT_HOLD_HOURS,
            "commission_rate": format(settings.PLATFORM_COMMISSION_RATE, "f"),
        },
        version=1,
    )
    db.add(intent)
    debit = _account(
        db,
        code=f"rental-provider-{order.currency}",
        owner_user_id=None,
        account_type="provider_clearing",
        currency=order.currency,
        normal_side="debit",
    )
    credit = _account(
        db,
        code=f"user-{order.supplier_id}-frozen-{order.currency}",
        owner_user_id=order.supplier_id,
        account_type="user_frozen",
        currency=order.currency,
        normal_side="credit",
    )
    journal = LedgerJournal(
        journal_no=_number("LJ"),
        event_type="server_rental_test_payment",
        reference_type="server_rental",
        reference_id=str(order.id),
        currency=order.currency,
        idempotency_key=f"ledger:{idempotency_key}",
        status="posted",
        metadata_payload={"order_no": order.order_no, "payment_mode": "placeholder"},
    )
    db.add(journal)
    db.flush()
    db.add_all([
        LedgerEntry(journal_id=journal.id, account_id=debit.id, direction="debit", amount=payment_amount),
        LedgerEntry(journal_id=journal.id, account_id=credit.id, direction="credit", amount=payment_amount),
    ])
    return intent


def _agent_command(
    db: Session, server: MerchantServer, lease: AccessLease, action: str, payload: dict
) -> AgentCommand:
    row = AgentCommand(
        command_no=_number("AC"),
        server_id=server.id,
        lease_id=lease.id,
        action=action,
        status="queued",
        payload=payload,
        attempts=0,
    )
    db.add(row)
    db.flush()
    if server.agent_mode == "local_simulator" and server.status == "online":
        row.status = "succeeded"
        row.attempts = 1
        row.completed_at = _now()
        row.result_message = "本机 Agent 模拟器已执行；未连接或修改真实服务器"
    return row


def _lease_username(server: MerchantServer, order_id: int) -> str:
    """Keep the account portable; Windows local account names are limited to 20 chars."""
    limit = 20 if server.agent_platform == "windows" else 32
    return f"{server.ssh_username}_{order_id}"[:limit]


def _real_payment_provider():
    provider = payment_provider()
    if provider.descriptor.provider == "pingxx":
        if not provider.descriptor.configured:
            raise ApiError("PAYMENT_NOT_CONFIGURED", "Ping++ 支付参数尚未配置完整", 503)
        return provider
    frontend_host = (urlparse(settings.FRONTEND_BASE_URL).hostname or "").casefold()
    api_host = (urlparse(settings.PUBLIC_API_BASE_URL).hostname or "").casefold()
    local_test = (
        provider.descriptor.provider == "disabled"
        and not settings.PAYMENT_PROVIDER_ENABLED
        and settings.APP_ENV.casefold() != "production"
        and settings.AGENT_LOCAL_SIMULATOR_ENABLED
        and frontend_host in {"127.0.0.1", "localhost", "::1"}
        and api_host in {"127.0.0.1", "localhost", "::1"}
    )
    if local_test:
        return None
    raise ApiError("PAYMENT_NOT_CONFIGURED", "生产环境必须配置真实支付服务", 503)


def payment_mode() -> str:
    provider = payment_provider()
    return provider.descriptor.provider if provider.descriptor.configured else "local_placeholder"


def create_direct_rental(
    db: Session,
    user: User,
    data: DirectServerRentalIn,
    *,
    idempotency_key: str,
    client_ip: str = "127.0.0.1",
) -> tuple[Order, AccessLease, PaymentIntent, bool]:
    ensure_verified_email(user)
    if user.role != "personal":
        raise ApiError("BUYER_REQUIRED", "只有买家账号可以租用服务器", 403)
    existing_intent = db.query(PaymentIntent).filter(
        PaymentIntent.idempotency_key == idempotency_key,
        PaymentIntent.user_id == user.id,
    ).first()
    if existing_intent is not None:
        order = db.get(Order, existing_intent.order_id)
        lease = db.query(AccessLease).filter(AccessLease.order_id == existing_intent.order_id).first()
        if order is None or lease is None:
            raise ApiError("DIRECT_RENTAL_CONFLICT", "租赁幂等记录不完整", 409)
        return order, lease, existing_intent, True

    provider = _real_payment_provider()

    key = db.query(BuyerSshKey).filter(
        BuyerSshKey.id == data.ssh_key_id,
        BuyerSshKey.user_id == user.id,
        BuyerSshKey.status == "active",
    ).first()
    if key is None:
        raise ApiError("SSH_KEY_NOT_AVAILABLE", "请选择一个有效的 SSH 公钥", 409)
    product = db.query(Product).filter(
        Product.id == data.product_id, Product.status == "published"
    ).with_for_update().first()
    if product is None:
        raise ApiError("PRODUCT_NOT_AVAILABLE", "服务器不存在或已经下架", 404)
    if product.supplier_id == user.id:
        raise ApiError("SELF_PURCHASE_FORBIDDEN", "不能租用自己发布的服务器", 409)
    server = db.query(MerchantServer).filter(
        MerchantServer.product_id == product.id,
        MerchantServer.status == "online",
    ).with_for_update().first()
    if server is not None:
        from app.services.agents import refresh_presence

        refresh_presence(server)
    if server is None:
        raise ApiError("SERVER_NOT_ONLINE", "服务器 Agent 当前不在线", 409)
    if server.status != "online":
        raise ApiError("SERVER_NOT_ONLINE", "服务器 Agent 心跳已经超时", 409)
    from app.services.agents import hardware_is_current, service_is_current

    if not hardware_is_current(server):
        raise ApiError("SERVER_HARDWARE_NOT_VERIFIED", "服务器实测配置尚未通过平台核验", 409)
    if not service_is_current(server):
        raise ApiError("SERVER_SSH_NOT_READY", "服务器 SSH 服务自检尚未通过", 409)
    occupied = db.query(AccessLease.id).filter(
        AccessLease.server_id == server.id,
        AccessLease.status.in_(("pending_authorization", "active", "grace")),
    ).first()
    if occupied or resource_service.available_quantity(db, product) < 1:
        raise ApiError("SERVER_ALREADY_RENTED", "这台服务器当前已被租用", 409)

    amount = product.unit_price * Decimal(data.duration_hours)
    if provider is not None and product.price_currency != "CNY":
        raise ApiError(
            "PAYMENT_CURRENCY_UNSUPPORTED",
            "Ping++ 当前按人民币分收款，请先把商品价格币种设置为 CNY",
            409,
        )
    now = _now()
    is_real_payment = provider is not None
    order = Order(
        order_no=_number("WO"),
        buyer_id=user.id,
        supplier_id=product.supplier_id,
        buy_request_id=None,
        accepted_quote_id=None,
        product_id=product.id,
        order_source="direct",
        environment="live",
        payment_status="pending" if is_real_payment else "paid",
        duration_hours=data.duration_hours,
        status="pending_confirmation" if is_real_payment else "delivered",
        amount=amount,
        currency=product.price_currency,
        price_unit="order_total",
        quantity=1,
        snapshot={
            "business_type": "dedicated_server_rental",
            "payment_mode": provider.descriptor.provider if is_real_payment else "local_placeholder",
            "product": {
                "resource_no": product.resource_no,
                "name": product.name,
                "gpu_model": product.gpu_model,
                "region": product.region,
                "unit_price": format(product.unit_price, "f"),
            },
            "server": {"server_no": server.server_no},
            "ssh_key_fingerprint": key.fingerprint_sha256,
        },
        buyer_confirmed_at=None if is_real_payment else now,
        supplier_confirmed_at=None if is_real_payment else now,
        confirmed_at=None if is_real_payment else now,
        delivery_started_at=None if is_real_payment else now,
        delivered_at=None if is_real_payment else now,
        delivery_note=None if is_real_payment else "买家 SSH 公钥已通过服务器 Agent 下发",
        version=1,
    )
    db.add(order)
    db.flush()
    resource_service.reserve_for_order(db, order, product.id, 1)
    if not is_real_payment:
        resource_service.allocate_for_order(db, order.id)
    lease = AccessLease(
        lease_no=_number("LS"),
        order_id=order.id,
        server_id=server.id,
        buyer_id=user.id,
        supplier_id=product.supplier_id,
        ssh_key_id=key.id,
        status="pending_authorization",
        connection_host=server.public_host,
        ssh_port=server.ssh_port,
        ssh_username=_lease_username(server, order.id),
        version=1,
    )
    db.add(lease)
    db.flush()
    if is_real_payment:
        intent = PaymentIntent(
            payment_no=_number("PI"),
            user_id=user.id,
            order_id=order.id,
            purpose="server_rental",
            amount=amount,
            currency=order.currency,
            status="created",
            provider=provider.descriptor.provider,
            idempotency_key=idempotency_key,
            metadata_payload={
                "return_path": "/account/leases",
                "lease_id": lease.id,
                "duration_hours": data.duration_hours,
                "client_ip": client_ip,
                "payment_channel": data.payment_channel,
            },
            version=1,
        )
        db.add(intent)
        db.flush()
        try:
            session = provider.create_checkout(PaymentRequest(
                payment_no=intent.payment_no,
                user_id=user.id,
                amount=amount,
                currency=order.currency,
                purpose=f"服务器租赁 {order.order_no}",
                return_url=f"{settings.FRONTEND_BASE_URL.rstrip('/')}/account/leases?payment={intent.payment_no}",
                idempotency_key=idempotency_key,
                client_ip=client_ip,
                channel=data.payment_channel,
            ))
        except ProviderUnavailable as exc:
            db.rollback()
            raise ApiError("PAYMENT_PROVIDER_UNAVAILABLE", "暂时无法创建 Ping++ 支付单", 503) from exc
        intent.provider_reference = session.provider_reference
        intent.checkout_url = session.checkout_url
        intent.expires_at = session.expires_at
        intent_metadata = dict(intent.metadata_payload or {})
        intent_metadata["provider_payload"] = dict(session.client_payload)
        intent.metadata_payload = intent_metadata
        intent.status = "provider_pending"
        intent.version += 1
        db.add(OrderEvent(
            order_id=order.id,
            actor_user_id=user.id,
            actor_role=user.role,
            event_type="payment_created",
            from_status=None,
            to_status="pending_confirmation",
            payload={"payment_no": intent.payment_no, "provider": provider.descriptor.provider},
        ))
        create_notification(
            db,
            user_id=user.id,
            category="order",
            title="服务器订单等待付款",
            body=f"订单 {order.order_no} 已预留服务器，请前往 Ping++ 收银台完成支付。",
            action_path="/account/orders",
        )
        _commit(db, "DIRECT_RENTAL_CONFLICT")
        db.refresh(order)
        db.refresh(lease)
        db.refresh(intent)
        return order, lease, intent, False

    command = _agent_command(db, server, lease, "authorize_key", {
        "username": lease.ssh_username,
        "public_key": key.public_key,
        "key_fingerprint": key.fingerprint_sha256,
        "duration_hours": data.duration_hours,
        "grace_hours": int(RENEWAL_GRACE.total_seconds() // 3600),
    })
    if command.status == "succeeded":
        lease.status = "active"
        lease.starts_at = now
        lease.authorized_at = now
        lease.expires_at = now + timedelta(hours=data.duration_hours)
        lease.grace_expires_at = lease.expires_at + RENEWAL_GRACE
    intent = _post_test_payment(db, order, idempotency_key=idempotency_key, purpose="server_rental")
    key.last_used_at = now
    db.add(OrderEvent(
        order_id=order.id,
        actor_user_id=user.id,
        actor_role="system",
        event_type="ssh_access_authorized" if lease.status == "active" else "ssh_access_queued",
        from_status="confirmed",
        to_status="delivered",
        payload={"lease_no": lease.lease_no, "key_fingerprint": key.fingerprint_sha256},
    ))
    create_notification(
        db,
        user_id=user.id,
        category="order",
        title="服务器访问权限已开通" if lease.status == "active" else "服务器访问权限正在开通",
        body=f"订单 {order.order_no} 已生成租约，私钥始终保留在你的设备上。",
        action_path="/account/leases",
    )
    create_notification(
        db,
        user_id=product.supplier_id,
        category="order",
        title="服务器产生新租约",
        body=f"服务器 {server.server_no} 已为订单 {order.order_no} 下发买家公钥。",
        action_path="/supplier/leases",
    )
    _commit(db, "DIRECT_RENTAL_CONFLICT")
    db.refresh(order)
    db.refresh(lease)
    return order, lease, intent, False


def _connection(lease: AccessLease) -> dict | None:
    if lease.status != "active":
        return None
    destination = f"{lease.ssh_username}@{lease.connection_host}"
    command = f"ssh {destination}" if lease.ssh_port == 22 else f"ssh -p {lease.ssh_port} {destination}"
    return {
        "host": lease.connection_host,
        "port": lease.ssh_port,
        "username": lease.ssh_username,
        "ssh_command": command,
    }


def lease_out(
    lease: AccessLease, order: Order, product: Product, key: BuyerSshKey,
    *, buyer_view: bool,
) -> dict:
    return {
        "id": lease.id,
        "lease_no": lease.lease_no,
        "order_id": order.id,
        "order_no": order.order_no,
        "product_id": product.id,
        "server_name": product.name,
        "gpu_model": product.gpu_model,
        "region": product.region,
        "status": lease.status,
        "duration_hours": order.duration_hours,
        "amount": format(order.amount, "f"),
        "currency": order.currency,
        "ssh_key": {"id": key.id, "name": key.name, "fingerprint": key.fingerprint_sha256},
        "connection": _connection(lease) if buyer_view else None,
        "starts_at": lease.starts_at,
        "expires_at": lease.expires_at,
        "grace_expires_at": lease.grace_expires_at,
        "authorized_at": lease.authorized_at,
        "access_revoked_at": lease.access_revoked_at,
        "failure_reason": lease.failure_reason,
        "created_at": lease.created_at,
        "version": lease.version,
        "renewable": lease.status in ("active", "grace"),
        "payment_mode": (order.snapshot or {}).get("payment_mode", "local_placeholder"),
    }


def apply_paid_intent(db: Session, intent: PaymentIntent) -> int:
    """Apply a verified rental/renewal payment and return the supplier ledger owner."""
    metadata = dict(intent.metadata_payload or {})
    order = db.query(Order).filter(Order.id == intent.order_id).with_for_update().first()
    if order is None:
        raise ApiError("PAYMENT_ORDER_NOT_FOUND", "支付关联订单不存在", 409)
    if metadata.get("fulfilled"):
        return order.supplier_id
    lease = db.query(AccessLease).filter(
        AccessLease.order_id == order.id
    ).with_for_update().first()
    if lease is None:
        raise ApiError("PAYMENT_LEASE_NOT_FOUND", "支付关联租约不存在", 409)
    server = db.get(MerchantServer, lease.server_id)
    key = db.get(BuyerSshKey, lease.ssh_key_id)
    product = db.get(Product, order.product_id)
    if server is None or key is None or product is None:
        raise ApiError("LEASE_DATA_INCOMPLETE", "服务器租约数据不完整", 409)
    now = _now()

    if intent.purpose == "server_rental":
        if order.payment_status != "paid":
            order.payment_status = "paid"
            order.status = "delivering"
            order.buyer_confirmed_at = now
            order.supplier_confirmed_at = now
            order.confirmed_at = now
            order.delivery_started_at = now
            order.version += 1
            resource_service.allocate_for_order(db, order.id)
            command = _agent_command(db, server, lease, "authorize_key", {
                "username": lease.ssh_username,
                "public_key": key.public_key,
                "key_fingerprint": key.fingerprint_sha256,
                "duration_hours": order.duration_hours,
                "grace_hours": int(RENEWAL_GRACE.total_seconds() // 3600),
            })
            if command.status == "succeeded":
                lease.status = "active"
                lease.starts_at = now
                lease.authorized_at = now
                lease.expires_at = now + timedelta(hours=order.duration_hours or 1)
                lease.grace_expires_at = lease.expires_at + RENEWAL_GRACE
                order.status = "delivered"
                order.delivered_at = now
                order.delivery_note = "支付确认后，买家 SSH 公钥已通过服务器 Agent 下发"
            key.last_used_at = now
            db.add(OrderEvent(
                order_id=order.id,
                actor_user_id=None,
                actor_role="system",
                event_type="payment_succeeded",
                from_status="pending_confirmation",
                to_status=order.status,
                payload={"payment_no": intent.payment_no, "provider": intent.provider},
            ))
            create_notification(
                db,
                user_id=order.buyer_id,
                category="order",
                title="付款成功，服务器权限正在开通" if lease.status != "active" else "服务器访问权限已开通",
                body=f"订单 {order.order_no} 已确认付款，私钥始终保留在你的设备上。",
                action_path="/account/leases",
            )
            create_notification(
                db,
                user_id=order.supplier_id,
                category="order",
                title="服务器订单已付款",
                body=f"订单 {order.order_no} 已通过 Ping++ 完成付款并开始下发买家公钥。",
                action_path="/supplier/leases",
            )
    elif intent.purpose == "lease_renewal":
        if lease.status not in ("active", "grace", "pending_authorization"):
            raise ApiError("LEASE_NOT_RENEWABLE", "租约在付款后已不再允许续费，请人工退款", 409)
        if key.status != "active":
            raise ApiError("SSH_KEY_REVOKED", "续费使用的 SSH 公钥已经撤销，请人工退款", 409)
        added_hours = int(metadata.get("duration_hours") or 0)
        if added_hours <= 0:
            raise ApiError("RENEWAL_METADATA_INVALID", "续费支付数据不完整", 409)
        was_grace = lease.status == "grace"
        metadata["renewal_rollback"] = {
            "order_amount": format(order.amount, "f"),
            "duration_hours": order.duration_hours,
            "expires_at": _aware(lease.expires_at).isoformat() if lease.expires_at else None,
            "grace_expires_at": (
                _aware(lease.grace_expires_at).isoformat() if lease.grace_expires_at else None
            ),
            "status": lease.status,
        }
        base = max(_aware(lease.expires_at) or now, now)
        order.amount += intent.amount
        order.duration_hours = (order.duration_hours or 0) + added_hours
        order.version += 1
        lease.expires_at = base + timedelta(hours=added_hours)
        lease.grace_expires_at = lease.expires_at + RENEWAL_GRACE
        lease.status = "active" if not was_grace else "pending_authorization"
        lease.access_revoked_at = None
        lease.version += 1
        if was_grace:
            command = _agent_command(db, server, lease, "authorize_key", {
                "username": lease.ssh_username,
                "public_key": key.public_key,
                "key_fingerprint": key.fingerprint_sha256,
                "duration_hours": added_hours,
                "expires_at": lease.expires_at.isoformat(),
                "grace_expires_at": lease.grace_expires_at.isoformat(),
            })
            if command.status == "succeeded":
                lease.status = "active"
                lease.authorized_at = now
        db.add(OrderEvent(
            order_id=order.id,
            actor_user_id=None,
            actor_role="system",
            event_type="lease_renewed",
            from_status=order.status,
            to_status=order.status,
            payload={
                "lease_no": lease.lease_no,
                "added_hours": added_hours,
                "payment_no": intent.payment_no,
            },
        ))
    else:
        raise ApiError("PAYMENT_PURPOSE_UNSUPPORTED", "支付业务尚未配置履约处理", 409)

    metadata["fulfilled"] = True
    intent.metadata_payload = metadata
    return order.supplier_id


def process_due_leases(db: Session, *, now: datetime | None = None) -> dict:
    current = now or _now()
    authorization_failed = 0
    revoked = 0
    cleaned = 0
    settled = 0
    timed_out_commands = db.query(AgentCommand).join(
        AccessLease, AccessLease.id == AgentCommand.lease_id
    ).filter(
        AgentCommand.action == "authorize_key",
        AgentCommand.status.in_(("queued", "running")),
        AgentCommand.created_at
        <= current - timedelta(seconds=settings.AGENT_AUTHORIZATION_TIMEOUT_SECONDS),
        AccessLease.status == "pending_authorization",
    ).with_for_update().all()
    for command in timed_out_commands:
        lease = db.get(AccessLease, command.lease_id)
        if lease is None:
            continue
        command.status = "failed"
        command.completed_at = current
        command.result_message = "Agent SSH 授权超时"
        lease.status = "failed"
        lease.failure_reason = command.result_message
        lease.version += 1
        intent = _intent_for_lease(db, lease)
        if intent is not None:
            request_compensation_refund(
                db,
                intent,
                lease,
                reason_code="SSH_AUTHORIZATION_TIMEOUT",
                reason=command.result_message,
            )
        authorization_failed += 1
    active_rows = db.query(AccessLease).filter(
        AccessLease.status == "active", AccessLease.expires_at <= current
    ).with_for_update().all()
    for lease in active_rows:
        server = db.get(MerchantServer, lease.server_id)
        if server is None:
            continue
        command = _agent_command(db, server, lease, "revoke_key", {
            "username": lease.ssh_username,
            "grace_expires_at": (_aware(lease.expires_at) + RENEWAL_GRACE).isoformat(),
        })
        lease.status = "grace"
        if command.status == "succeeded":
            lease.access_revoked_at = current
        lease.grace_expires_at = _aware(lease.expires_at) + RENEWAL_GRACE
        lease.version += 1
        revoked += 1
    grace_rows = db.query(AccessLease).filter(
        AccessLease.status == "grace", AccessLease.grace_expires_at <= current
    ).with_for_update().all()
    for lease in grace_rows:
        server = db.get(MerchantServer, lease.server_id)
        order = db.get(Order, lease.order_id)
        if server is not None:
            command = _agent_command(
                db, server, lease, "cleanup_account", {"username": lease.ssh_username}
            )
        else:
            command = None
        lease.status = "expired"
        if command is not None and command.status == "succeeded":
            lease.cleanup_completed_at = current
        lease.version += 1
        if order is not None:
            if order.status not in ("completed", "cancelled"):
                order.status = "completed"
                order.completed_at = current
                order.version += 1
            resource_service.release_for_order(db, order.id, "租约续费宽限期结束")
        cleaned += 1
    matured_intents = db.query(PaymentIntent).join(
        AccessLease, AccessLease.order_id == PaymentIntent.order_id
    ).filter(
        PaymentIntent.purpose.in_(("server_rental", "lease_renewal")),
        PaymentIntent.status == "succeeded",
        AccessLease.expires_at.is_not(None),
        AccessLease.expires_at
        <= current - timedelta(hours=settings.SETTLEMENT_HOLD_HOURS),
    ).with_for_update().all()
    for intent in matured_intents:
        if release_frozen_payment(db, intent, now=current):
            settled += 1
    if authorization_failed or revoked or cleaned or settled:
        _commit(db)
    return {
        "authorization_failed": authorization_failed,
        "access_revoked": revoked,
        "accounts_cleaned": cleaned,
        "payments_settled": settled,
    }


def list_leases(db: Session, user: User, *, scope: str) -> list[tuple[AccessLease, Order, Product, BuyerSshKey]]:
    process_due_leases(db)
    query = db.query(AccessLease, Order, Product, BuyerSshKey).join(
        Order, Order.id == AccessLease.order_id
    ).join(Product, Product.id == Order.product_id).join(
        BuyerSshKey, BuyerSshKey.id == AccessLease.ssh_key_id
    )
    if scope == "buyer":
        query = query.filter(AccessLease.buyer_id == user.id)
    elif scope == "supplier":
        application = db.query(SupplierApplication.id).filter(
            SupplierApplication.user_id == user.id,
            SupplierApplication.status == "approved",
        ).first()
        if user.role != "supplier" or application is None:
            raise ApiError("SUPPLIER_REQUIRED", "只有已审核商家可以查看服务器租约", 403)
        query = query.filter(AccessLease.supplier_id == user.id)
    else:
        raise ValueError("unsupported lease scope")
    return query.order_by(AccessLease.created_at.desc(), AccessLease.id.desc()).all()


def renew_lease(
    db: Session,
    user: User,
    lease_id: int,
    data: LeaseRenewIn,
    *,
    idempotency_key: str,
    client_ip: str = "127.0.0.1",
) -> tuple[AccessLease, Order, Product, BuyerSshKey, PaymentIntent, bool]:
    ensure_verified_email(user)
    process_due_leases(db)
    existing = db.query(PaymentIntent).filter(
        PaymentIntent.idempotency_key == idempotency_key,
        PaymentIntent.user_id == user.id,
    ).first()
    lease = db.query(AccessLease).filter(
        AccessLease.id == lease_id, AccessLease.buyer_id == user.id
    ).with_for_update().first()
    if lease is None:
        raise ApiError("LEASE_NOT_FOUND", "服务器租约不存在", 404)
    order = db.get(Order, lease.order_id)
    product = db.get(Product, order.product_id) if order else None
    key = db.get(BuyerSshKey, lease.ssh_key_id)
    server = db.get(MerchantServer, lease.server_id)
    if order is None or product is None or key is None or server is None:
        raise ApiError("LEASE_DATA_INCOMPLETE", "服务器租约数据不完整", 409)
    if existing is not None:
        return lease, order, product, key, existing, True
    if lease.version != data.version:
        raise ApiError("LEASE_VERSION_CONFLICT", "租约已更新，请刷新后重试", 409)
    if lease.status not in ("active", "grace"):
        raise ApiError("LEASE_NOT_RENEWABLE", "当前租约不能续费", 409)
    if key.status != "active":
        raise ApiError("SSH_KEY_REVOKED", "租约使用的 SSH 公钥已经撤销", 409)
    if server.status != "online":
        raise ApiError("SERVER_NOT_ONLINE", "服务器 Agent 当前不在线，暂时不能续费", 409)

    provider = _real_payment_provider()
    if provider is not None and order.currency != "CNY":
        raise ApiError(
            "PAYMENT_CURRENCY_UNSUPPORTED",
            "Ping++ 当前按人民币分收款，请先把商品价格币种设置为 CNY",
            409,
        )

    added_amount = product.unit_price * Decimal(data.duration_hours)
    if provider is not None:
        intent = PaymentIntent(
            payment_no=_number("PI"),
            user_id=user.id,
            order_id=order.id,
            purpose="lease_renewal",
            amount=added_amount,
            currency=order.currency,
            status="created",
            provider=provider.descriptor.provider,
            idempotency_key=idempotency_key,
            metadata_payload={
                "return_path": "/account/leases",
                "lease_id": lease.id,
                "duration_hours": data.duration_hours,
                "client_ip": client_ip,
                "payment_channel": data.payment_channel,
            },
            version=1,
        )
        db.add(intent)
        db.flush()
        try:
            session = provider.create_checkout(PaymentRequest(
                payment_no=intent.payment_no,
                user_id=user.id,
                amount=added_amount,
                currency=order.currency,
                purpose=f"服务器续费 {lease.lease_no}",
                return_url=f"{settings.FRONTEND_BASE_URL.rstrip('/')}/account/leases?payment={intent.payment_no}",
                idempotency_key=idempotency_key,
                client_ip=client_ip,
                channel=data.payment_channel,
            ))
        except ProviderUnavailable as exc:
            db.rollback()
            raise ApiError("PAYMENT_PROVIDER_UNAVAILABLE", "暂时无法创建 Ping++ 续费支付单", 503) from exc
        intent.provider_reference = session.provider_reference
        intent.checkout_url = session.checkout_url
        intent.expires_at = session.expires_at
        intent_metadata = dict(intent.metadata_payload or {})
        intent_metadata["provider_payload"] = dict(session.client_payload)
        intent.metadata_payload = intent_metadata
        intent.status = "provider_pending"
        intent.version += 1
        _commit(db, "LEASE_RENEWAL_CONFLICT")
        db.refresh(intent)
        return lease, order, product, key, intent, False

    now = _now()
    was_grace = lease.status == "grace"
    base = max(_aware(lease.expires_at) or now, now)
    order.amount += added_amount
    order.duration_hours = (order.duration_hours or 0) + data.duration_hours
    order.version += 1
    lease.expires_at = base + timedelta(hours=data.duration_hours)
    lease.grace_expires_at = lease.expires_at + RENEWAL_GRACE
    lease.status = "active"
    lease.access_revoked_at = None
    lease.version += 1
    command = _agent_command(db, server, lease, "authorize_key", {
        "username": lease.ssh_username,
        "public_key": key.public_key,
        "key_fingerprint": key.fingerprint_sha256,
        "duration_hours": data.duration_hours,
        "expires_at": lease.expires_at.isoformat(),
        "grace_expires_at": lease.grace_expires_at.isoformat(),
    })
    if was_grace:
        if command.status != "succeeded":
            lease.status = "pending_authorization"
    intent = _post_test_payment(
        db,
        order,
        idempotency_key=idempotency_key,
        purpose="lease_renewal",
        amount=added_amount,
    )
    intent.provider_reference = f"placeholder:renew:{lease.lease_no}"
    intent.metadata_payload = {
        **(intent.metadata_payload or {}),
        "duration_hours": data.duration_hours,
        "fulfilled": True,
    }
    db.add(OrderEvent(
        order_id=order.id,
        actor_user_id=user.id,
        actor_role=user.role,
        event_type="lease_renewed",
        from_status=order.status,
        to_status=order.status,
        payload={"lease_no": lease.lease_no, "added_hours": data.duration_hours},
    ))
    _commit(db, "LEASE_RENEWAL_CONFLICT")
    db.refresh(lease)
    db.refresh(order)
    return lease, order, product, key, intent, False


def list_supplier_servers(db: Session, user: User) -> list[tuple[MerchantServer, Product]]:
    application = db.query(SupplierApplication.id).filter(
        SupplierApplication.user_id == user.id,
        SupplierApplication.status == "approved",
    ).first()
    if user.role != "supplier" or application is None:
        raise ApiError("SUPPLIER_REQUIRED", "只有已审核商家可以查看服务器", 403)
    return db.query(MerchantServer, Product).join(
        Product, Product.id == MerchantServer.product_id
    ).filter(MerchantServer.supplier_id == user.id).order_by(MerchantServer.created_at.desc()).all()


def server_out(server: MerchantServer, product: Product) -> dict:
    from app.services.agents import hardware_out, refresh_presence, service_out

    refresh_presence(server)
    return {
        "id": server.id,
        "server_no": server.server_no,
        "product_id": product.id,
        "product_name": product.name,
        "resource_status": product.status,
        "public_host": server.public_host,
        "ssh_port": server.ssh_port,
        "ssh_username_prefix": server.ssh_username,
        "status": server.status,
        "agent_mode": server.agent_mode,
        "agent_version": server.agent_version,
        "agent_device_id": server.agent_device_id,
        "agent_platform": server.agent_platform,
        "agent_arch": server.agent_arch,
        "agent_hostname": server.agent_hostname,
        "agent_capabilities": server.agent_capabilities or [],
        "agent_enrolled_at": server.agent_enrolled_at,
        "last_seen_at": server.last_seen_at,
        "hardware": hardware_out(server),
        "services": service_out(server),
        "created_at": server.created_at,
        "version": server.version,
    }
