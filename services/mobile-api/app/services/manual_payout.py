"""Closed-test, human-reviewed bank payout workflow.

This module never talks to a bank.  It records an application, freezes only
the separately tracked withdrawable bucket, and lets an explicitly authorised
finance operator attest to an external manual transfer with a private receipt.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import secrets
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.sensitive import fingerprint, last_four, reveal, sensitive_capability_enabled
from app.models.bank_card import BankCard, REGISTERED_CARD_STATUSES, public_bank_card_status
from app.models.ledger import Ledger
from app.models.user import User
from app.models.verification import Verification
from app.models.wallet import Wallet
from app.models.withdrawal import (
    FinanceAuditLog,
    PaymentInstructionGrant,
    PayoutReceipt,
    WithdrawalOrder,
)
from app.utils.response import BizError


ACTIVE_WITHDRAWAL_STATUSES = ("reviewing", "manual_payment_pending")
FINAL_WITHDRAWAL_STATUSES = ("paid", "rejected", "failed", "canceled")
ALL_WITHDRAWAL_STATUSES = ACTIVE_WITHDRAWAL_STATUSES + FINAL_WITHDRAWAL_STATUSES
AMOUNT_QUANTUM = Decimal("0.000001")
CNY_QUANTUM = Decimal("0.01")


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _decimal_setting(value: float) -> Decimal:
    return Decimal(str(value))


def payout_rate() -> Decimal:
    return _decimal_setting(settings.PAYOUT_CARD_HOUR_RMB_RATE).quantize(AMOUNT_QUANTUM)


def payout_fee_rate() -> Decimal:
    value = _decimal_setting(settings.PAYOUT_FEE_RATE)
    if value < 0 or value >= 1:
        raise BizError("提现费率配置无效")
    return value


def payout_bounds() -> tuple[Decimal, Decimal]:
    bounds = (
        _decimal_setting(settings.PAYOUT_MIN_CARD_HOURS).quantize(AMOUNT_QUANTUM),
        _decimal_setting(settings.PAYOUT_MAX_CARD_HOURS).quantize(AMOUNT_QUANTUM),
    )
    if bounds[0] <= 0 or bounds[1] < bounds[0]:
        raise BizError("提现金额上下限配置无效")
    return bounds


def withdrawal_config() -> dict:
    minimum, maximum = payout_bounds()
    return {
        "enabled": sensitive_capability_enabled(settings.MANUAL_PAYOUT_ENABLED),
        "manual_transfer": True,
        "bank_verified": False,
        "rate_cny_per_card_hour": float(payout_rate()),
        "fee_rate": float(payout_fee_rate()),
        "min_card_hours": float(minimum),
        "max_card_hours": float(maximum),
        "statuses": list(ALL_WITHDRAWAL_STATUSES),
        "notice": "银行卡仅登记且未经银行验证；实名审核通过后可申请，财务复核收款人并手工打款",
    }


def record_audit(
    db: Session,
    actor_user_id: int,
    action: str,
    object_type: str,
    object_id: int,
    detail: dict | None = None,
) -> None:
    # Details must contain identifiers/status only.  Callers must never place a
    # full card or identity number in this log.
    serialized = json.dumps(detail, ensure_ascii=False, separators=(",", ":")) if detail else None
    if serialized and re.search(r"(?<!\d)\d{12,19}(?!\d)", serialized):
        raise BizError("审计备注不得包含银行卡号或身份证号格式的连续数字")
    if serialized and len(serialized) > 2000:
        raise BizError("审计备注过长")
    db.add(FinanceAuditLog(
        actor_user_id=actor_user_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        detail=serialized,
    ))


def _ledger_event(
    db: Session,
    *,
    order: WithdrawalOrder,
    wallet: Wallet,
    event: str,
    direction: str,
    remark: str,
) -> Ledger:
    key = f"withdrawal:{order.id}:{event}"
    existing = db.query(Ledger).filter(Ledger.event_key == key).first()
    if existing:
        return existing
    entry = Ledger(
        user_id=order.user_id,
        wallet_id=wallet.id,
        type=f"withdraw_{event}",
        direction=direction,
        amount=order.amount_card_hours,
        balance_after=wallet.balance,
        ref_order_id=order.id,
        event_key=key,
        remark=remark,
    )
    db.add(entry)
    return entry


def _amounts(amount_card_hours: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    amount = amount_card_hours.quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise BizError("提现卡时必须大于 0")
    minimum, maximum = payout_bounds()
    if amount < minimum or amount > maximum:
        raise BizError(f"提现卡时需在 {minimum} 至 {maximum} 之间")
    rate = payout_rate()
    gross = (amount * rate).quantize(CNY_QUANTUM, rounding=ROUND_HALF_UP)
    fee = (gross * payout_fee_rate()).quantize(CNY_QUANTUM, rounding=ROUND_HALF_UP)
    net = gross - fee
    if net <= 0:
        raise BizError("提现到账金额必须大于 0")
    return amount, rate, gross, fee


def _new_order_no() -> str:
    return "WODW" + utc_now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:10].upper()


def _masked_card(card: BankCard | None, order: WithdrawalOrder) -> dict:
    return {
        "id": order.bank_card_id,
        "bank_name": order.bank_name_snapshot,
        "card_number": f"**** **** **** {order.card_last4_snapshot}",
        "card_last4": order.card_last4_snapshot,
        "holder": order.holder_snapshot,
        "status": public_bank_card_status(card.status) if card else "disabled",
        "verification_mode": "format_only",
        "bank_verified": False,
    }


def order_out(db: Session, order: WithdrawalOrder) -> dict:
    card = db.query(BankCard).filter(BankCard.id == order.bank_card_id).first()
    receipt = db.query(PayoutReceipt).filter(PayoutReceipt.withdrawal_id == order.id).first()
    return {
        "id": order.id,
        "order_no": order.order_no,
        "status": order.status,
        "amount_card_hours": float(order.amount_card_hours),
        "locked_rate_cny": float(order.locked_rate_cny),
        "gross_amount_cny": float(order.gross_amount_cny),
        "fee_cny": float(order.fee_cny),
        "net_amount_cny": float(order.net_amount_cny),
        "bank_card": _masked_card(card, order),
        "review_note": order.review_note,
        "failure_reason": order.failure_reason,
        "bank_reference": order.bank_reference,
        "paid_amount_cny": float(order.paid_amount_cny) if order.paid_amount_cny is not None else None,
        "paid_at": order.paid_at,
        "receipt_available": receipt is not None,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }


def _payment_instruction_ttl_seconds() -> int:
    ttl = int(settings.PAYOUT_INSTRUCTION_REVEAL_TTL_SECONDS)
    if ttl < 30 or ttl > 1800:
        raise BizError("付款信息查看凭证有效期配置无效")
    return ttl


def _payment_instruction_snapshot(order: WithdrawalOrder, card: BankCard) -> str:
    """Digest the exact payout subject without persisting sensitive values."""
    material = {
        "withdrawal_id": order.id,
        "order_version": order.version,
        "bank_card_id": card.id,
        "card_fingerprint": fingerprint(reveal(card.card_number)),
        "phone_fingerprint": fingerprint(reveal(card.phone)),
        "bank_name": card.bank_name,
        "holder": card.holder,
        "status": card.status,
        "verification_mode": card.verification_mode,
        "card_updated_at": card.updated_at.isoformat(timespec="microseconds") if card.updated_at else None,
    }
    serialized = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def issue_payment_instruction_grant(
    db: Session,
    order: WithdrawalOrder,
    card: BankCard,
    actor: User,
) -> tuple[str, datetime, int]:
    """Create a short-lived one-time proof for this exact reveal operation."""
    token = secrets.token_urlsafe(32)
    expires_at = utc_now() + timedelta(seconds=_payment_instruction_ttl_seconds())
    grant = PaymentInstructionGrant(
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        actor_user_id=actor.id,
        withdrawal_id=order.id,
        bank_card_id=card.id,
        order_version=order.version,
        card_snapshot_hash=_payment_instruction_snapshot(order, card),
        expires_at=expires_at,
    )
    db.add(grant)
    db.flush()
    return token, expires_at, grant.id


def _consume_payment_instruction_grant(
    db: Session,
    order: WithdrawalOrder,
    actor: User,
    token: str,
) -> None:
    normalized = token.strip()
    if not normalized or len(normalized) > 512:
        raise BizError("付款信息查看凭证无效或已过期，请重新受控查看", status_code=409)
    card = db.query(BankCard).filter(BankCard.id == order.bank_card_id).first()
    if not card:
        raise BizError("银行卡资料不存在", status_code=404)
    now = utc_now()
    changed = db.query(PaymentInstructionGrant).filter(
        PaymentInstructionGrant.token_hash == hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        PaymentInstructionGrant.actor_user_id == actor.id,
        PaymentInstructionGrant.withdrawal_id == order.id,
        PaymentInstructionGrant.bank_card_id == card.id,
        PaymentInstructionGrant.order_version == order.version,
        PaymentInstructionGrant.card_snapshot_hash == _payment_instruction_snapshot(order, card),
        PaymentInstructionGrant.expires_at > now,
        PaymentInstructionGrant.used_at.is_(None),
    ).update({PaymentInstructionGrant.used_at: now}, synchronize_session=False)
    if changed != 1:
        db.rollback()
        raise BizError("付款信息查看凭证无效或已过期，请重新受控查看", status_code=409)


def create_withdrawal(
    db: Session,
    user: User,
    *,
    amount_card_hours: Decimal,
    bank_card_id: int,
    client_request_id: str,
) -> WithdrawalOrder:
    if not sensitive_capability_enabled(settings.MANUAL_PAYOUT_ENABLED):
        raise BizError("人工提现申请尚未启用", status_code=503)

    amount, rate, gross, fee = _amounts(amount_card_hours)
    net = gross - fee
    existing = db.query(WithdrawalOrder).filter(
        WithdrawalOrder.user_id == user.id,
        WithdrawalOrder.client_request_id == client_request_id,
    ).first()
    if existing:
        if existing.bank_card_id != bank_card_id or Decimal(existing.amount_card_hours) != amount:
            raise BizError("该请求编号已用于其他提现申请", status_code=409)
        return existing

    verification = db.query(Verification).filter(
        Verification.user_id == user.id,
        Verification.status == "verified",
    ).first()
    if not verification:
        raise BizError("实名认证人工审核通过后才能申请提现")

    card = db.query(BankCard).filter(
        BankCard.id == bank_card_id,
        BankCard.user_id == user.id,
        BankCard.status.in_(REGISTERED_CARD_STATUSES),
    ).first()
    if not card:
        raise BizError("请选择已登记且未停用的银行卡")
    if verification.real_name != card.holder:
        raise BizError("收款人姓名与已通过的实名认证不一致")
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
    if not wallet:
        raise BizError("钱包不存在", status_code=404)

    order = WithdrawalOrder(
        order_no=_new_order_no(),
        user_id=user.id,
        wallet_id=wallet.id,
        bank_card_id=card.id,
        client_request_id=client_request_id,
        status="reviewing",
        amount_card_hours=amount,
        locked_rate_cny=rate,
        gross_amount_cny=gross,
        fee_cny=fee,
        net_amount_cny=net,
        bank_name_snapshot=card.bank_name,
        card_last4_snapshot=last_four(card.card_number),
        holder_snapshot=card.holder,
    )
    db.add(order)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        concurrent = db.query(WithdrawalOrder).filter(
            WithdrawalOrder.user_id == user.id,
            WithdrawalOrder.client_request_id == client_request_id,
        ).first()
        if concurrent and concurrent.bank_card_id == bank_card_id and Decimal(concurrent.amount_card_hours) == amount:
            return concurrent
        raise BizError("提现申请重复，请查询原申请", status_code=409)

    # One conditional statement is the concurrency boundary.  It prevents two
    # simultaneous requests from both spending the same withdrawable amount,
    # including on SQLite where SELECT FOR UPDATE is ineffective.
    updated = db.query(Wallet).filter(
        Wallet.id == wallet.id,
        Wallet.balance >= amount,
        Wallet.withdrawable_balance >= amount,
    ).update({
        Wallet.balance: Wallet.balance - amount,
        Wallet.frozen: Wallet.frozen + amount,
        Wallet.withdrawable_balance: Wallet.withdrawable_balance - amount,
        Wallet.withdraw_frozen: Wallet.withdraw_frozen + amount,
    }, synchronize_session=False)
    if updated != 1:
        db.rollback()
        raise BizError("可提现余额不足")
    db.expire(wallet)
    _ledger_event(
        db, order=order, wallet=wallet, event="freeze", direction="out",
        remark=f"提现申请冻结 {order.order_no}",
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = db.query(WithdrawalOrder).filter(
            WithdrawalOrder.user_id == user.id,
            WithdrawalOrder.client_request_id == client_request_id,
        ).first()
        if concurrent and concurrent.bank_card_id == bank_card_id and Decimal(concurrent.amount_card_hours) == amount:
            return concurrent
        raise BizError("提现申请重复，请查询原申请", status_code=409)
    db.refresh(order)
    return order


def approve_withdrawal(db: Session, order: WithdrawalOrder, actor: User, note: str | None) -> None:
    changed = db.query(WithdrawalOrder).filter(
        WithdrawalOrder.id == order.id,
        WithdrawalOrder.status == "reviewing",
    ).update({
        WithdrawalOrder.status: "manual_payment_pending",
        WithdrawalOrder.review_note: note,
        WithdrawalOrder.reviewed_by: actor.id,
        WithdrawalOrder.reviewed_at: utc_now(),
        WithdrawalOrder.version: WithdrawalOrder.version + 1,
    }, synchronize_session=False)
    if changed != 1:
        db.rollback()
        raise BizError("申请状态已变化，请刷新", status_code=409)
    record_audit(db, actor.id, "withdrawal.approve", "withdrawal", order.id, {"note": note})
    db.commit()


def _unfreeze_to_status(
    db: Session,
    order: WithdrawalOrder,
    *,
    status: str,
    allowed_from: tuple[str, ...],
    reason: str,
    actor: User | None,
) -> None:
    changed = db.query(WithdrawalOrder).filter(
        WithdrawalOrder.id == order.id,
        WithdrawalOrder.status.in_(allowed_from),
    ).update({
        WithdrawalOrder.status: status,
        WithdrawalOrder.failure_reason: reason,
        WithdrawalOrder.reviewed_by: actor.id if actor else order.reviewed_by,
        WithdrawalOrder.reviewed_at: utc_now(),
        WithdrawalOrder.version: WithdrawalOrder.version + 1,
    }, synchronize_session=False)
    if changed != 1:
        db.rollback()
        raise BizError("申请状态已变化，请刷新", status_code=409)
    amount = Decimal(order.amount_card_hours)
    restored = db.query(Wallet).filter(
        Wallet.id == order.wallet_id,
        Wallet.frozen >= amount,
        Wallet.withdraw_frozen >= amount,
    ).update({
        Wallet.balance: Wallet.balance + amount,
        Wallet.frozen: Wallet.frozen - amount,
        Wallet.withdrawable_balance: Wallet.withdrawable_balance + amount,
        Wallet.withdraw_frozen: Wallet.withdraw_frozen - amount,
    }, synchronize_session=False)
    if restored != 1:
        db.rollback()
        raise BizError("冻结余额异常，已停止状态变更", status_code=409)
    wallet = db.query(Wallet).filter(Wallet.id == order.wallet_id).first()
    _ledger_event(
        db, order=order, wallet=wallet, event="unfreeze", direction="in",
        remark=f"提现{status}解冻 {order.order_no}: {reason}",
    )
    if actor:
        record_audit(db, actor.id, f"withdrawal.{status}", "withdrawal", order.id, {"reason": reason})
    db.commit()


def reject_withdrawal(db: Session, order: WithdrawalOrder, actor: User, reason: str) -> None:
    _unfreeze_to_status(
        db, order, status="rejected", allowed_from=("reviewing",), reason=reason, actor=actor,
    )


def fail_withdrawal(db: Session, order: WithdrawalOrder, actor: User, reason: str) -> None:
    _unfreeze_to_status(
        db, order, status="failed", allowed_from=("manual_payment_pending",), reason=reason, actor=actor,
    )


def cancel_withdrawal(db: Session, order: WithdrawalOrder, user: User) -> None:
    if order.user_id != user.id:
        raise BizError("提现申请不存在", status_code=404)
    _unfreeze_to_status(
        db, order, status="canceled", allowed_from=("reviewing",), reason="用户取消", actor=None,
    )


def normalize_paid_at(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def mark_paid(
    db: Session,
    order: WithdrawalOrder,
    actor: User,
    *,
    receipt_path: Path,
    original_name: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
    bank_reference: str,
    paid_amount_cny: Decimal,
    paid_at: datetime,
    payee_confirmed: bool,
    reveal_token: str,
) -> None:
    if not payee_confirmed:
        raise BizError("请先确认已核对收款人姓名与银行卡登记信息")
    reference = bank_reference.strip()
    if not re.fullmatch(r"[A-Za-z0-9._:/-]{4,128}", reference):
        raise BizError("请填写有效的银行流水号")
    if not paid_amount_cny.is_finite():
        raise BizError("实付金额格式无效")
    paid_amount = paid_amount_cny.quantize(CNY_QUANTUM, rounding=ROUND_HALF_UP)
    if paid_amount != Decimal(order.net_amount_cny).quantize(CNY_QUANTUM):
        raise BizError("实付金额必须与申请到账金额一致")
    paid_time = normalize_paid_at(paid_at)
    now = utc_now()
    if paid_time < order.created_at or paid_time > now + timedelta(minutes=5):
        raise BizError("付款时间必须在申请创建后且不能晚于当前时间")
    if db.query(PayoutReceipt).filter(PayoutReceipt.withdrawal_id == order.id).first():
        raise BizError("该申请已有打款凭证", status_code=409)
    if db.query(WithdrawalOrder).filter(
        WithdrawalOrder.bank_reference == reference,
        WithdrawalOrder.id != order.id,
    ).first():
        raise BizError("该银行流水号已用于其他提现申请", status_code=409)

    # A client checkbox is not proof of a sensitive-data reveal. Consume the
    # server-issued, actor-bound grant in the same transaction as mark-paid.
    _consume_payment_instruction_grant(db, order, actor, reveal_token)
    record_audit(
        db, actor.id, "withdrawal.payment_instructions.consume", "withdrawal", order.id,
        {"card_id": order.bank_card_id},
    )

    changed = db.query(WithdrawalOrder).filter(
        WithdrawalOrder.id == order.id,
        WithdrawalOrder.status == "manual_payment_pending",
    ).update({
        WithdrawalOrder.status: "paid",
        WithdrawalOrder.bank_reference: reference,
        WithdrawalOrder.paid_amount_cny: paid_amount,
        WithdrawalOrder.paid_at: paid_time,
        WithdrawalOrder.paid_by: actor.id,
        WithdrawalOrder.version: WithdrawalOrder.version + 1,
    }, synchronize_session=False)
    if changed != 1:
        db.rollback()
        raise BizError("申请状态已变化，请刷新", status_code=409)
    amount = Decimal(order.amount_card_hours)
    settled = db.query(Wallet).filter(
        Wallet.id == order.wallet_id,
        Wallet.frozen >= amount,
        Wallet.withdraw_frozen >= amount,
    ).update({
        Wallet.frozen: Wallet.frozen - amount,
        Wallet.withdraw_frozen: Wallet.withdraw_frozen - amount,
    }, synchronize_session=False)
    if settled != 1:
        db.rollback()
        raise BizError("冻结余额异常，已停止确认到账", status_code=409)
    db.add(PayoutReceipt(
        withdrawal_id=order.id,
        storage_path=str(receipt_path),
        original_name=Path(original_name).name[:255] or f"receipt-{order.order_no}",
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        uploaded_by=actor.id,
    ))
    wallet = db.query(Wallet).filter(Wallet.id == order.wallet_id).first()
    _ledger_event(
        db, order=order, wallet=wallet, event="success", direction="internal",
        remark=f"财务确认手工打款 {order.order_no}（冻结转已支付，不重复扣余额）",
    )
    record_audit(
        db, actor.id, "withdrawal.mark_paid", "withdrawal", order.id,
        {
            "bank_reference_tail": reference[-4:],
            "bank_reference_sha256": hashlib.sha256(reference.encode("utf-8")).hexdigest(),
            "amount_cny": str(paid_amount),
            "receipt_sha256": sha256,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise BizError("银行流水号或打款凭证已被其他申请使用", status_code=409)


def validate_receipt(content: bytes) -> tuple[str, str]:
    if not content:
        raise BizError("请选择打款凭证")
    if len(content) > settings.PAYOUT_RECEIPT_MAX_BYTES:
        raise BizError("打款凭证不能超过 5MB")
    if content.startswith(b"%PDF-"):
        # A complete PDF must contain an EOF marker near the end.  This is not
        # an antivirus scanner, but rejects renamed arbitrary files.
        if b"%%EOF" not in content[-2048:]:
            raise BizError("PDF 凭证已损坏或格式无效")
        return "application/pdf", "pdf"
    if content.startswith(b"\xff\xd8\xff"):
        expected, mime, suffix = "JPEG", "image/jpeg", "jpg"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        expected, mime, suffix = "PNG", "image/png", "png"
    else:
        raise BizError("凭证仅支持真实的 JPG、PNG 或 PDF")
    try:
        with Image.open(io.BytesIO(content)) as image:
            actual = (image.format or "").upper()
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise BizError("图片凭证已损坏或格式无效")
    if actual != expected:
        raise BizError("凭证文件签名与实际格式不一致")
    return mime, suffix


def persist_receipt(content: bytes, order: WithdrawalOrder, suffix: str) -> tuple[Path, str]:
    root = (
        Path(settings.UPLOAD_ROOT).expanduser().resolve()
        if settings.UPLOAD_ROOT
        else Path(__file__).resolve().parents[2] / "uploads"
    ) / "payout_receipts"
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"payout_{order.id}_{uuid.uuid4().hex}.{suffix}"
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=root, prefix=".payout_", suffix=".tmp", delete=False) as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_name = tmp.name
        os.replace(temp_name, destination)
        temp_name = None
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    return destination, hashlib.sha256(content).hexdigest()
