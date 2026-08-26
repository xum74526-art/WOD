import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import finance_admin_user_ids, get_current_platform, get_current_user, require_finance_admin
from app.core.sensitive import (
    mask_id_card,
    reveal as reveal_sensitive_value,
    sensitive_capability_enabled,
)
from app.db.session import get_db
from app.models.bank_card import BankCard, REGISTERED_CARD_STATUSES, public_bank_card_status
from app.models.user import User
from app.models.verification import Verification
from app.models.withdrawal import FinanceAuditLog, PayoutReceipt, WithdrawalOrder
from app.schemas.withdrawal import (
    ApproveWithdrawalIn,
    FailedWithdrawalIn,
    FinanceReviewIn,
    RejectWithdrawalIn,
)
from app.services.manual_payout import (
    ALL_WITHDRAWAL_STATUSES,
    approve_withdrawal,
    fail_withdrawal,
    issue_payment_instruction_grant,
    mark_paid,
    order_out,
    persist_receipt,
    record_audit,
    reject_withdrawal,
    validate_receipt,
)
from app.routers.verification import ocr_public_summary
from app.utils.response import BizError, success
from app.services.auth_session import AuditPlatform, normalize_platform
from app.services.invite_rewards_v2 import reevaluate_invitee_qualification


router = APIRouter(prefix="/api/finance", tags=["finance"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _assert_not_self(actor: User, owner_user_id: int) -> None:
    if actor.id == owner_user_id:
        raise BizError("财务管理员不能审核或打款自己的资料/申请", status_code=403)


def _page(page: int, page_size: int) -> None:
    if page < 1 or page_size < 1 or page_size > 100:
        raise BizError("分页参数无效")


@router.get("/me")
def finance_me(user: User = Depends(get_current_user)):
    return success({
        "is_finance_admin": user.id in finance_admin_user_ids(),
        "manual_bank_card_enabled": sensitive_capability_enabled(settings.MANUAL_BANK_CARD_ENABLED),
        "manual_payout_enabled": sensitive_capability_enabled(settings.MANUAL_PAYOUT_ENABLED),
    })


@router.get("/audit-logs")
def audit_logs(
    action_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
    actor: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
):
    _page(page, page_size)
    query = db.query(FinanceAuditLog)
    if action_filter:
        query = query.filter(FinanceAuditLog.action == action_filter[:64])
    total = query.count()
    rows = query.order_by(FinanceAuditLog.created_at.desc(), FinanceAuditLog.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    items = []
    for row in rows:
        operator = db.query(User).filter(User.id == row.actor_user_id).first()
        try:
            detail = json.loads(row.detail) if row.detail else None
        except (TypeError, json.JSONDecodeError):
            detail = None
        items.append({
            "id": row.id,
            "actor_user_id": row.actor_user_id,
            "actor_username": operator.username if operator else None,
            "action": row.action,
            "object_type": row.object_type,
            "object_id": row.object_id,
            "detail": detail,
            "created_at": row.created_at,
        })
    return success({"total": total, "page": page, "page_size": page_size, "items": items})


def _verification_out(db: Session, row: Verification) -> dict:
    owner = db.query(User).filter(User.id == row.user_id).first()
    payload = {
        "id": row.id,
        "user_id": row.user_id,
        "username": owner.username if owner else None,
        "real_name": row.real_name,
        "id_card_masked": mask_id_card(row.id_card),
        "status": row.status,
        "reject_reason": row.reject_reason,
        "front_photo_uploaded": bool(row.front_photo),
        "back_photo_uploaded": bool(row.back_photo),
        "consent_recorded": bool(row.consent_at),
        "created_platform": row.created_platform or "legacy",
        "last_modified_platform": row.last_modified_platform or "legacy",
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    payload.update(ocr_public_summary(row))
    return payload


@router.get("/verifications")
def verification_list(
    status_filter: str | None = "pending",
    page: int = 1,
    page_size: int = 20,
    platform: AuditPlatform | None = None,
    actor: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
):
    _page(page, page_size)
    if status_filter and status_filter not in {"pending", "verified", "rejected"}:
        raise BizError("实名认证状态无效")
    query = db.query(Verification)
    if status_filter:
        query = query.filter(Verification.status == status_filter)
    if platform:
        query = query.filter(Verification.created_platform == platform)
    total = query.count()
    rows = query.order_by(Verification.created_at.asc(), Verification.id.asc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return success({"total": total, "page": page, "page_size": page_size, "items": [
        _verification_out(db, row) for row in rows
    ]})


def _verification(db: Session, verification_id: int) -> Verification:
    row = db.query(Verification).filter(Verification.id == verification_id).first()
    if not row:
        raise BizError("实名认证申请不存在", status_code=404)
    return row


@router.get("/verifications/{verification_id}")
def verification_detail(
    verification_id: int,
    actor: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
):
    row = _verification(db, verification_id)
    record_audit(db, actor.id, "verification.view", "verification", row.id)
    db.commit()
    return success(_verification_out(db, row))


@router.post("/verifications/{verification_id}/review")
def verification_review(
    verification_id: int,
    data: FinanceReviewIn,
    actor: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    row = _verification(db, verification_id)
    _assert_not_self(actor, row.user_id)
    if row.status not in {"pending", "rejected"}:
        raise BizError("该实名认证申请已完成审核", status_code=409)
    if data.approved:
        if not row.consent_at:
            raise BizError("缺少敏感信息单独同意记录，请用户重新提交实名认证", status_code=409)
        if not row.front_photo or not row.back_photo:
            raise BizError("正反面身份证照片齐全后才能人工审核通过")
        row.status = "verified"
        row.reject_reason = None
        action = "verification.approve"
    else:
        reason = (data.reason or "").strip()
        if len(reason) < 2:
            raise BizError("驳回时请填写原因")
        row.status = "rejected"
        row.reject_reason = reason
        action = "verification.reject"
    row.last_modified_platform = normalize_platform(platform)
    record_audit(db, actor.id, action, "verification", row.id, {
        "reason": data.reason,
        "ocr_status_at_review": row.ocr_status or "not_started",
        "ocr_matched": row.ocr_status == "matched",
    })
    if data.approved:
        # Identity-first and order-first flows share the same idempotent V2
        # qualification service. This path must not create retroactive order
        # commission; it only completes the qualification and fixed bonus.
        reevaluate_invitee_qualification(row.user_id, db, event_at=_utcnow())
    db.commit()
    db.refresh(row)
    return success(_verification_out(db, row))


@router.get("/verifications/{verification_id}/photo/{side}")
def verification_photo(
    verification_id: int,
    side: str,
    actor: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
):
    row = _verification(db, verification_id)
    _assert_not_self(actor, row.user_id)
    if side not in {"front", "back"}:
        raise BizError("证件照片类型无效", status_code=404)
    filename = row.front_photo if side == "front" else row.back_photo
    if not filename:
        raise BizError("证件照片未上传", status_code=404)
    root = (
        Path(settings.UPLOAD_ROOT).expanduser().resolve()
        if settings.UPLOAD_ROOT
        else Path(__file__).resolve().parents[2] / "uploads"
    ) / "id_cards"
    path = (root / Path(filename).name).resolve()
    if path.parent != root.resolve() or not path.is_file():
        raise BizError("证件照片不存在", status_code=404)
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(path.suffix.lower())
    if not mime:
        raise BizError("证件照片格式无效", status_code=404)
    record_audit(db, actor.id, f"verification.photo.{side}", "verification", row.id)
    db.commit()
    return FileResponse(
        path,
        media_type=mime,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )


def _bank_card_out(db: Session, card: BankCard) -> dict:
    owner = db.query(User).filter(User.id == card.user_id).first()
    plain = reveal_sensitive_value(card.card_number)
    return {
        "id": card.id,
        "user_id": card.user_id,
        "username": owner.username if owner else None,
        "bank_name": card.bank_name,
        "card_number": f"**** **** **** {plain[-4:]}",
        "card_last4": plain[-4:],
        "holder": card.holder,
        "phone": ((lambda phone: phone[:3] + "****" + phone[-4:] if phone else None)(reveal_sensitive_value(card.phone))),
        "is_default": card.is_default,
        "status": public_bank_card_status(card.status),
        "verification_mode": card.verification_mode or "legacy_unvalidated",
        "bank_verified": False,
        "reject_reason": card.review_reason,
        "reviewed_at": card.reviewed_at,
        "created_platform": card.created_platform or "legacy",
        "last_modified_platform": card.last_modified_platform or "legacy",
        "created_at": card.created_at,
    }


@router.get("/bank-cards")
def bank_card_list(
    status_filter: str | None = "registered",
    page: int = 1,
    page_size: int = 20,
    platform: AuditPlatform | None = None,
    actor: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
):
    _page(page, page_size)
    valid = {"registered", "pending_review", "active", "rejected", "disabled"}
    if status_filter and status_filter not in valid:
        raise BizError("银行卡状态无效")
    query = db.query(BankCard)
    if status_filter == "registered":
        query = query.filter(BankCard.status.in_(REGISTERED_CARD_STATUSES))
    elif status_filter:
        query = query.filter(BankCard.status == status_filter)
    if platform:
        query = query.filter(BankCard.created_platform == platform)
    total = query.count()
    rows = query.order_by(BankCard.created_at.asc(), BankCard.id.asc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return success({"total": total, "page": page, "page_size": page_size, "items": [
        _bank_card_out(db, row) for row in rows
    ]})


@router.post("/bank-cards/{card_id}/review")
def bank_card_review(
    card_id: int,
    data: FinanceReviewIn,
    actor: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    if not sensitive_capability_enabled(settings.MANUAL_BANK_CARD_ENABLED):
        raise BizError("银行卡登记复核尚未启用", status_code=503)
    card = db.query(BankCard).filter(BankCard.id == card_id).first()
    if not card:
        raise BizError("银行卡不存在", status_code=404)
    _assert_not_self(actor, card.user_id)
    if card.status not in {"pending_review", "rejected"}:
        raise BizError("该银行卡当前不需要登记复核", status_code=409)
    if data.approved:
        verification = db.query(Verification).filter(
            Verification.user_id == card.user_id,
            Verification.status == "verified",
        ).first()
        if not verification:
            raise BizError("用户实名认证通过后才能确认银行卡登记")
        if verification.real_name != card.holder:
            raise BizError("持卡人姓名与实名认证不一致")
        card.status = "registered"
        card.verification_mode = "format_only"
        card.review_reason = None
        if not db.query(BankCard).filter(
            BankCard.user_id == card.user_id,
            BankCard.status.in_(REGISTERED_CARD_STATUSES),
            BankCard.is_default.is_(True),
            BankCard.id != card.id,
        ).first():
            card.is_default = True
        action = "bank_card.approve"
    else:
        reason = (data.reason or "").strip()
        if len(reason) < 2:
            raise BizError("驳回时请填写原因")
        card.status = "rejected"
        card.is_default = False
        card.review_reason = reason
        action = "bank_card.reject"
    card.reviewed_by = actor.id
    card.reviewed_at = _utcnow()
    card.last_modified_platform = normalize_platform(platform)
    record_audit(db, actor.id, action, "bank_card", card.id, {"reason": data.reason})
    db.commit()
    db.refresh(card)
    return success(_bank_card_out(db, card))


def _withdrawal(db: Session, order_id: int) -> WithdrawalOrder:
    row = db.query(WithdrawalOrder).filter(WithdrawalOrder.id == order_id).first()
    if not row:
        raise BizError("提现申请不存在", status_code=404)
    return row


def _finance_order_out(db: Session, order: WithdrawalOrder) -> dict:
    output = order_out(db, order)
    owner = db.query(User).filter(User.id == order.user_id).first()
    output["user"] = {"id": order.user_id, "username": owner.username if owner else None}
    return output


@router.get("/withdrawals")
def withdrawal_list(
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
    platform: AuditPlatform | None = None,
    actor: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
):
    _page(page, page_size)
    if status_filter and status_filter not in ALL_WITHDRAWAL_STATUSES:
        raise BizError("提现状态无效")
    query = db.query(WithdrawalOrder)
    if status_filter:
        query = query.filter(WithdrawalOrder.status == status_filter)
    if platform:
        query = query.filter(WithdrawalOrder.created_platform == platform)
    total = query.count()
    rows = query.order_by(WithdrawalOrder.created_at.desc(), WithdrawalOrder.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return success({"total": total, "page": page, "page_size": page_size, "items": [
        _finance_order_out(db, row) for row in rows
    ]})


@router.get("/withdrawals/{order_id}")
def withdrawal_detail(
    order_id: int,
    actor: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
):
    order = _withdrawal(db, order_id)
    record_audit(db, actor.id, "withdrawal.view", "withdrawal", order.id)
    db.commit()
    return success(_finance_order_out(db, order))


@router.post("/withdrawals/{order_id}/approve")
def withdrawal_approve(
    order_id: int,
    data: ApproveWithdrawalIn,
    actor: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    if not sensitive_capability_enabled(settings.MANUAL_PAYOUT_ENABLED):
        raise BizError("人工提现尚未启用", status_code=503)
    order = _withdrawal(db, order_id)
    _assert_not_self(actor, order.user_id)
    approve_withdrawal(db, order, actor, data.note, platform=normalize_platform(platform))
    db.refresh(order)
    return success(_finance_order_out(db, order))


@router.post("/withdrawals/{order_id}/reject")
def withdrawal_reject(
    order_id: int,
    data: RejectWithdrawalIn,
    actor: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    order = _withdrawal(db, order_id)
    _assert_not_self(actor, order.user_id)
    reject_withdrawal(db, order, actor, data.reason, platform=normalize_platform(platform))
    db.refresh(order)
    return success(_finance_order_out(db, order))


@router.post("/withdrawals/{order_id}/mark-failed")
def withdrawal_failed(
    order_id: int,
    data: FailedWithdrawalIn,
    actor: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    order = _withdrawal(db, order_id)
    _assert_not_self(actor, order.user_id)
    fail_withdrawal(db, order, actor, data.reason, platform=normalize_platform(platform))
    db.refresh(order)
    return success(_finance_order_out(db, order))


@router.get("/withdrawals/{order_id}/payment-instructions")
def payment_instructions(
    order_id: int,
    reveal_card: bool = Query(False, alias="reveal"),
    actor: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
):
    # Accept the documented ?reveal=true while retaining a non-reserved Python
    # argument name for direct unit tests.
    if not reveal_card:
        raise BizError("查看完整卡号需显式传入 reveal=true")
    order = _withdrawal(db, order_id)
    _assert_not_self(actor, order.user_id)
    if order.status != "manual_payment_pending":
        raise BizError("仅待人工打款申请可查看付款信息", status_code=409)
    card = db.query(BankCard).filter(BankCard.id == order.bank_card_id).first()
    if not card:
        raise BizError("银行卡资料不存在", status_code=404)
    card_number = reveal_sensitive_card(card)
    reveal_token, reveal_expires_at, grant_id = issue_payment_instruction_grant(
        db, order, card, actor,
    )
    record_audit(db, actor.id, "withdrawal.reveal_payment_instructions", "withdrawal", order.id, {
        "card_id": card.id,
        "grant_id": grant_id,
        "expires_at": reveal_expires_at.isoformat(timespec="seconds"),
    })
    db.commit()
    return success({
        "order_id": order.id,
        "order_no": order.order_no,
        "bank_name": order.bank_name_snapshot,
        "card_number": card_number,
        "holder": order.holder_snapshot,
        "phone": reveal_sensitive_value(card.phone),
        "amount_cny": float(order.net_amount_cny),
        "verification_mode": "format_only",
        "bank_verified": False,
        "reveal_token": reveal_token,
        "reveal_expires_at": reveal_expires_at,
        "notice": "银行卡仅为已登记资料，未经银行验证；财务打款前须核对收款人姓名、银行名称和卡号，查看操作已记录审计日志",
    })


def reveal_sensitive_card(card: BankCard) -> str:
    value = "".join(reveal_sensitive_value(card.card_number).split())
    if len(value) < 12:
        raise BizError("银行卡敏感数据无法解密", status_code=409)
    return value


@router.post("/withdrawals/{order_id}/mark-paid")
async def withdrawal_mark_paid(
    order_id: int,
    receipt: UploadFile = File(...),
    bank_reference: str = Form(...),
    paid_amount_cny: str = Form(...),
    paid_at: datetime = Form(...),
    payee_confirmed: bool = Form(...),
    reveal_token: str = Form(...),
    actor: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    if not sensitive_capability_enabled(settings.MANUAL_PAYOUT_ENABLED):
        raise BizError("人工提现尚未启用", status_code=503)
    order = _withdrawal(db, order_id)
    _assert_not_self(actor, order.user_id)
    content = await receipt.read(settings.PAYOUT_RECEIPT_MAX_BYTES + 1)
    mime, suffix = validate_receipt(content)
    try:
        amount = Decimal(paid_amount_cny)
    except (InvalidOperation, ValueError):
        raise BizError("实付金额格式无效")
    path, sha256 = persist_receipt(content, order, suffix)
    try:
        mark_paid(
            db,
            order,
            actor,
            receipt_path=path,
            original_name=receipt.filename or f"receipt.{suffix}",
            content_type=mime,
            size_bytes=len(content),
            sha256=sha256,
            bank_reference=bank_reference,
            paid_amount_cny=amount,
            paid_at=paid_at,
            payee_confirmed=payee_confirmed,
            reveal_token=reveal_token,
            platform=normalize_platform(platform),
        )
    except Exception:
        if path.is_file():
            path.unlink()
        raise
    db.refresh(order)
    return success(_finance_order_out(db, order))


@router.get("/withdrawals/{order_id}/receipt")
def withdrawal_receipt(
    order_id: int,
    actor: User = Depends(require_finance_admin),
    db: Session = Depends(get_db),
):
    order = _withdrawal(db, order_id)
    _assert_not_self(actor, order.user_id)
    receipt = db.query(PayoutReceipt).filter(PayoutReceipt.withdrawal_id == order.id).first()
    if not receipt:
        raise BizError("打款凭证不存在", status_code=404)
    path = Path(receipt.storage_path).resolve()
    root = (
        Path(settings.UPLOAD_ROOT).expanduser().resolve()
        if settings.UPLOAD_ROOT
        else Path(__file__).resolve().parents[2] / "uploads"
    ) / "payout_receipts"
    if path.parent != root.resolve() or not path.is_file():
        raise BizError("打款凭证文件不存在", status_code=404)
    record_audit(db, actor.id, "withdrawal.receipt.read", "withdrawal", order.id, {
        "receipt_sha256": receipt.sha256,
    })
    db.commit()
    return FileResponse(
        path,
        media_type=receipt.content_type,
        filename=Path(receipt.original_name).name,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )
