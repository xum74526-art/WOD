import base64
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    LedgerAccount,
    LedgerEntry,
    LedgerJournal,
    SupplierApplication,
    SupplierWithdrawal,
    User,
)
from app.security import ApiError
from app.services.internal_modules import create_notification
from app.settlement_schemas import SupplierWithdrawalCreateIn


logger = logging.getLogger("app.settlements")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _number(prefix: str) -> str:
    return f"{prefix}{_now():%Y%m%d}{uuid4().hex[:12].upper()}"


def _money(value: Decimal) -> str:
    return format(value, "f")


def _approved_supplier(db: Session, user: User) -> None:
    approved = db.query(SupplierApplication.id).filter(
        SupplierApplication.user_id == user.id,
        SupplierApplication.status == "approved",
    ).first()
    if user.role != "supplier" or approved is None:
        raise ApiError("SUPPLIER_REQUIRED", "只有已审核商家可以申请结算", 403)
    from app.services.manual_kyc import approved_for_user

    if not approved_for_user(db, user.id):
        raise ApiError("SUPPLIER_KYC_REQUIRED", "完成实名认证后才能查看收益或申请提现", 403)


def _cipher() -> AESGCM:
    # Development can use SECRET_KEY so local flows remain testable. Production
    # readiness requires an independent key so session-key rotation does not
    # make bank details unreadable.
    source = settings.PAYOUT_ENCRYPTION_KEY or settings.SECRET_KEY
    key = hashlib.sha256(f"wod-payout-v1:{source}".encode()).digest()
    return AESGCM(key)


def _encrypt_details(details: dict[str, str]) -> str:
    nonce = os.urandom(12)
    plaintext = json.dumps(details, ensure_ascii=False, separators=(",", ":")).encode()
    ciphertext = _cipher().encrypt(nonce, plaintext, b"wod-supplier-payout-v1")
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def _decrypt_details(value: str) -> dict[str, str]:
    try:
        raw = base64.urlsafe_b64decode(value.encode())
        plaintext = _cipher().decrypt(raw[:12], raw[12:], b"wod-supplier-payout-v1")
        result = json.loads(plaintext)
        if not isinstance(result, dict):
            raise ValueError("invalid payout details")
        return {str(key): str(item) for key, item in result.items()}
    except Exception as exc:
        raise ApiError("PAYOUT_DETAILS_UNAVAILABLE", "结算账户信息无法解密，请检查加密密钥", 500) from exc


def _account(
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


def _balance(db: Session, account: LedgerAccount) -> Decimal:
    rows = db.query(LedgerEntry).filter(LedgerEntry.account_id == account.id).all()
    return sum(
        (
            entry.amount if entry.direction == account.normal_side else -entry.amount
            for entry in rows
        ),
        Decimal("0"),
    )


def _journal(
    db: Session,
    *,
    row: SupplierWithdrawal,
    event_type: str,
    suffix: str,
    entries: list[tuple[LedgerAccount, str, Decimal]],
    metadata: dict | None = None,
) -> LedgerJournal:
    key = f"withdrawal:{row.withdrawal_no}:{suffix}"
    existing = db.query(LedgerJournal).filter(LedgerJournal.idempotency_key == key).first()
    if existing is not None:
        return existing
    debits = sum((amount for _, side, amount in entries if side == "debit"), Decimal("0"))
    credits = sum((amount for _, side, amount in entries if side == "credit"), Decimal("0"))
    if not entries or debits <= 0 or debits != credits:
        raise ApiError("LEDGER_NOT_BALANCED", "提现账本借贷不平衡", 409)
    journal = LedgerJournal(
        journal_no=_number("LJ"),
        event_type=event_type,
        reference_type="supplier_withdrawal",
        reference_id=str(row.id),
        currency=row.currency,
        idempotency_key=key,
        status="posted",
        metadata_payload={"withdrawal_no": row.withdrawal_no, **(metadata or {})},
    )
    db.add(journal)
    db.flush()
    for account, side, amount in entries:
        if side not in {"debit", "credit"} or amount <= 0 or account.currency != row.currency:
            raise ApiError("LEDGER_ENTRY_INVALID", "提现账本分录无效", 409)
        db.add(LedgerEntry(
            journal_id=journal.id,
            account_id=account.id,
            direction=side,
            amount=amount,
        ))
    return journal


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.exception(
            "supplier withdrawal transaction conflict",
            extra={"event": "supplier_withdrawal_conflict"},
        )
        raise ApiError("WITHDRAWAL_CONFLICT", "提现记录发生冲突，请刷新后重试", 409) from exc


def _accounts(db: Session, supplier_id: int, currency: str) -> tuple[LedgerAccount, LedgerAccount]:
    available = _account(
        db,
        code=f"user-{supplier_id}-available-{currency}",
        owner_user_id=supplier_id,
        account_type="user_available",
        currency=currency,
        normal_side="credit",
    )
    frozen = _account(
        db,
        code=f"user-{supplier_id}-frozen-{currency}",
        owner_user_id=supplier_id,
        account_type="user_frozen",
        currency=currency,
        normal_side="credit",
    )
    return available, frozen


def withdrawal_out(row: SupplierWithdrawal, *, reveal_account: bool = False) -> dict:
    details = _decrypt_details(row.payout_details_encrypted)
    payout = {
        "method": row.payout_method,
        "beneficiary_name": details.get("beneficiary_name"),
        "bank_name": details.get("bank_name"),
        "account_no": details.get("bank_account_no") if reveal_account else f"****{row.payout_account_last4}",
    }
    return {
        "id": row.id,
        "withdrawal_no": row.withdrawal_no,
        "supplier_id": row.supplier_id,
        "amount": _money(row.amount),
        "currency": row.currency,
        "status": row.status,
        "payout": payout,
        "review_note": row.review_note,
        "payment_reference": row.payment_reference,
        "requested_at": row.requested_at,
        "reviewed_at": row.reviewed_at,
        "paid_at": row.paid_at,
        "cancelled_at": row.cancelled_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "version": row.version,
    }


def list_supplier_withdrawals(db: Session, user: User) -> list[SupplierWithdrawal]:
    _approved_supplier(db, user)
    return db.query(SupplierWithdrawal).filter(
        SupplierWithdrawal.supplier_id == user.id
    ).order_by(SupplierWithdrawal.created_at.desc(), SupplierWithdrawal.id.desc()).limit(100).all()


def revenue_snapshot(db: Session, user: User) -> dict:
    # This keeps local and single-instance deployments self-healing when the
    # supplier opens the balance page. Production may invoke the same function
    # from an independent scheduler without changing settlement semantics.
    from app.services.server_rentals import process_due_leases

    process_due_leases(db)
    rows = list_supplier_withdrawals(db, user)
    accounts = db.query(LedgerAccount).filter(
        LedgerAccount.owner_user_id == user.id,
        LedgerAccount.status != "closed",
    ).all()
    currencies: dict[str, dict[str, Decimal]] = {}
    for account in accounts:
        values = currencies.setdefault(
            account.currency, {"available": Decimal("0"), "frozen": Decimal("0")}
        )
        if account.account_type == "user_available":
            values["available"] += _balance(db, account)
        elif account.account_type == "user_frozen":
            values["frozen"] += _balance(db, account)
    if not currencies:
        currencies["CNY"] = {"available": Decimal("0"), "frozen": Decimal("0")}
    return {
        "balances": [
            {"currency": code, "available": _money(value["available"]), "frozen": _money(value["frozen"])}
            for code, value in sorted(currencies.items())
        ],
        "summary": {
            "requested": _money(sum((row.amount for row in rows if row.status in {"requested", "approved"}), Decimal("0"))),
            "paid": _money(sum((row.amount for row in rows if row.status == "paid"), Decimal("0"))),
        },
        "withdrawals": [withdrawal_out(row) for row in rows],
        "settlement_mode": "manual_bank_transfer",
        "policy": {
            "commission_rate": format(settings.PLATFORM_COMMISSION_RATE, "f"),
            "settlement_hold_hours": settings.SETTLEMENT_HOLD_HOURS,
            "dispute_holds_settlement": True,
        },
    }


def create_withdrawal(
    db: Session,
    user: User,
    data: SupplierWithdrawalCreateIn,
    *,
    idempotency_key: str,
) -> SupplierWithdrawal:
    _approved_supplier(db, user)
    details = {
        "beneficiary_name": data.beneficiary_name.strip(),
        "bank_name": data.bank_name.strip(),
        "bank_account_no": data.bank_account_no,
    }
    existing = db.query(SupplierWithdrawal).filter(
        SupplierWithdrawal.idempotency_key == idempotency_key
    ).first()
    if existing is not None:
        if (
            existing.supplier_id != user.id
            or existing.amount != data.amount
            or existing.currency != data.currency
            or _decrypt_details(existing.payout_details_encrypted) != details
        ):
            raise ApiError("IDEMPOTENCY_KEY_REUSED", "这个幂等键已经用于不同的提现申请", 409)
        return existing

    available, frozen = _accounts(db, user.id, data.currency)
    db.query(LedgerAccount).filter(LedgerAccount.id == available.id).with_for_update().one()
    if _balance(db, available) < data.amount:
        raise ApiError("INSUFFICIENT_BALANCE", "商家可用余额不足", 409)
    row = SupplierWithdrawal(
        withdrawal_no=_number("WD"),
        supplier_id=user.id,
        amount=data.amount,
        currency=data.currency,
        status="requested",
        payout_method="manual_bank_transfer",
        payout_details_encrypted=_encrypt_details(details),
        payout_account_last4=data.bank_account_no[-4:],
        idempotency_key=idempotency_key,
    )
    db.add(row)
    db.flush()
    _journal(
        db,
        row=row,
        event_type="supplier_withdrawal_reserved",
        suffix="reserve",
        entries=[(available, "debit", row.amount), (frozen, "credit", row.amount)],
    )
    create_notification(
        db,
        user_id=user.id,
        category="payment",
        title="提现申请已提交",
        body=f"提现 {row.currency} {_money(row.amount)} 已冻结，等待管理员审核。",
        action_path="/supplier/revenue",
    )
    _commit(db)
    db.refresh(row)
    return row


def _owned(db: Session, user: User, withdrawal_id: int, *, lock: bool = False) -> SupplierWithdrawal:
    _approved_supplier(db, user)
    query = db.query(SupplierWithdrawal).filter(
        SupplierWithdrawal.id == withdrawal_id,
        SupplierWithdrawal.supplier_id == user.id,
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise ApiError("WITHDRAWAL_NOT_FOUND", "提现申请不存在", 404)
    return row


def cancel_withdrawal(db: Session, user: User, withdrawal_id: int, *, version: int) -> SupplierWithdrawal:
    row = _owned(db, user, withdrawal_id, lock=True)
    if row.version != version:
        raise ApiError("WITHDRAWAL_VERSION_CONFLICT", "提现记录已更新，请刷新后重试", 409)
    if row.status != "requested":
        raise ApiError("WITHDRAWAL_NOT_CANCELLABLE", "只有待审核提现可以取消", 409)
    available, frozen = _accounts(db, row.supplier_id, row.currency)
    row.status = "cancelled"
    row.cancelled_at = _now()
    row.version += 1
    _journal(
        db,
        row=row,
        event_type="supplier_withdrawal_cancelled",
        suffix="cancel",
        entries=[(frozen, "debit", row.amount), (available, "credit", row.amount)],
    )
    _commit(db)
    db.refresh(row)
    return row


def list_admin_withdrawals(db: Session, *, status: str | None = None) -> list[tuple[SupplierWithdrawal, User, SupplierApplication | None]]:
    query = db.query(SupplierWithdrawal, User, SupplierApplication).join(
        User, User.id == SupplierWithdrawal.supplier_id
    ).outerjoin(SupplierApplication, SupplierApplication.user_id == User.id)
    if status:
        query = query.filter(SupplierWithdrawal.status == status)
    return query.order_by(SupplierWithdrawal.created_at.desc(), SupplierWithdrawal.id.desc()).limit(200).all()


def _admin_row(db: Session, withdrawal_id: int) -> SupplierWithdrawal:
    row = db.query(SupplierWithdrawal).filter(
        SupplierWithdrawal.id == withdrawal_id
    ).with_for_update().first()
    if row is None:
        raise ApiError("WITHDRAWAL_NOT_FOUND", "提现申请不存在", 404)
    return row


def approve_withdrawal(db: Session, admin: User, withdrawal_id: int, *, version: int, note: str | None) -> SupplierWithdrawal:
    row = _admin_row(db, withdrawal_id)
    if row.version != version:
        raise ApiError("WITHDRAWAL_VERSION_CONFLICT", "提现记录已更新，请刷新后重试", 409)
    if row.status != "requested":
        raise ApiError("WITHDRAWAL_NOT_REVIEWABLE", "只有待审核提现可以批准", 409)
    row.status = "approved"
    row.reviewed_by_user_id = admin.id
    row.reviewed_at = _now()
    row.review_note = note.strip() if note else None
    row.version += 1
    create_notification(
        db,
        user_id=row.supplier_id,
        category="payment",
        title="提现申请已通过审核",
        body=f"提现 {row.withdrawal_no} 已通过审核，等待财务线下打款。",
        action_path="/supplier/revenue",
    )
    _commit(db)
    db.refresh(row)
    return row


def reject_withdrawal(db: Session, admin: User, withdrawal_id: int, *, version: int, note: str) -> SupplierWithdrawal:
    row = _admin_row(db, withdrawal_id)
    if row.version != version:
        raise ApiError("WITHDRAWAL_VERSION_CONFLICT", "提现记录已更新，请刷新后重试", 409)
    if row.status not in {"requested", "approved"}:
        raise ApiError("WITHDRAWAL_NOT_REVIEWABLE", "当前提现不能驳回", 409)
    available, frozen = _accounts(db, row.supplier_id, row.currency)
    row.status = "rejected"
    row.reviewed_by_user_id = admin.id
    row.reviewed_at = _now()
    row.review_note = note.strip()
    row.version += 1
    _journal(
        db,
        row=row,
        event_type="supplier_withdrawal_rejected",
        suffix="reject",
        entries=[(frozen, "debit", row.amount), (available, "credit", row.amount)],
        metadata={"reviewed_by": admin.id},
    )
    create_notification(
        db,
        user_id=row.supplier_id,
        category="payment",
        title="提现申请未通过",
        body=f"提现 {row.withdrawal_no} 已驳回，冻结金额已退回可用余额。",
        action_path="/supplier/revenue",
    )
    _commit(db)
    db.refresh(row)
    return row


def complete_withdrawal(
    db: Session,
    admin: User,
    withdrawal_id: int,
    *,
    version: int,
    payment_reference: str,
    note: str | None,
) -> SupplierWithdrawal:
    row = _admin_row(db, withdrawal_id)
    if row.version != version:
        raise ApiError("WITHDRAWAL_VERSION_CONFLICT", "提现记录已更新，请刷新后重试", 409)
    if row.status != "approved":
        raise ApiError("WITHDRAWAL_NOT_PAYABLE", "只有已审核提现可以登记打款", 409)
    _, frozen = _accounts(db, row.supplier_id, row.currency)
    clearing = _account(
        db,
        code=f"manual-payout-clearing-{row.currency}",
        owner_user_id=None,
        account_type="provider_clearing",
        currency=row.currency,
        normal_side="debit",
    )
    row.status = "paid"
    row.payment_reference = payment_reference.strip()
    row.review_note = note.strip() if note else row.review_note
    row.paid_at = _now()
    row.version += 1
    _journal(
        db,
        row=row,
        event_type="supplier_withdrawal_paid",
        suffix="paid",
        entries=[(frozen, "debit", row.amount), (clearing, "credit", row.amount)],
        metadata={"payment_reference": row.payment_reference, "paid_by": admin.id},
    )
    create_notification(
        db,
        user_id=row.supplier_id,
        category="payment",
        title="提现已打款",
        body=f"提现 {row.withdrawal_no} 已完成，银行流水号：{row.payment_reference}。",
        action_path="/supplier/revenue",
    )
    _commit(db)
    db.refresh(row)
    return row
