"""Auditable recharge-vs-promotional allocation for wallet-funded commerce."""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.order_funding import OrderFundingAllocation
from app.models.order_renewal import OrderRenewal
from app.models.wallet import Wallet
from app.services.wallet_balance import spendable_wallet_balance
from app.utils.response import BizError


FUNDING_POLICY_VERSION = "wallet-funding-v1"
LEGACY_UNKNOWN_FUNDING_POLICY_VERSION = "legacy-unknown-promotional-v1"
_SCALE = Decimal("0.000001")


def funding_amount(value: Decimal | float | int | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(_SCALE, rounding=ROUND_HALF_UP)


def assert_wallet_funding_invariants(wallet: Wallet, db: Session) -> None:
    """Fail closed if promotional sub-buckets no longer match their parents."""

    balance = funding_amount(wallet.balance)
    frozen = funding_amount(wallet.frozen)
    promotional = funding_amount(wallet.promotional_balance)
    promotional_frozen = funding_amount(wallet.promotional_frozen)
    spendable = funding_amount(spendable_wallet_balance(wallet, db))
    if min(balance, frozen, promotional, promotional_frozen) < 0:
        raise BizError("钱包资金分层异常，请联系平台服务人员核查", status_code=409)
    if promotional > spendable or promotional_frozen > frozen:
        raise BizError("钱包促销余额分层异常，请联系平台服务人员核查", status_code=409)


def _snapshot(*, legacy_unknown: bool = False) -> dict:
    return {
        "spend_priority": "promotional_first",
        "cash_definition": "recharge_backed_wallet_card_hours",
        "promotional_withdrawable": False,
        "merchant_settlement_basis": "full_gross_amount",
        "promotional_merchant_treatment": "platform_subsidy",
        "legacy_unknown_classification": "promotional" if legacy_unknown else None,
    }


def _existing(db: Session, source_type: str, source_id: int) -> OrderFundingAllocation | None:
    return db.query(OrderFundingAllocation).filter(
        OrderFundingAllocation.source_type == source_type,
        OrderFundingAllocation.source_id == source_id,
    ).with_for_update().first()


def _new_allocation(
    db: Session,
    *,
    order: Order,
    renewal: OrderRenewal | None,
    wallet: Wallet,
    gross: Decimal,
    promotional: Decimal,
    status: str,
    policy_version: str = FUNDING_POLICY_VERSION,
    legacy_unknown: bool = False,
) -> OrderFundingAllocation:
    cash = funding_amount(gross - promotional)
    allocation = OrderFundingAllocation(
        source_type="renewal" if renewal is not None else "order",
        source_id=renewal.id if renewal is not None else order.id,
        order_id=order.id,
        order_renewal_id=renewal.id if renewal is not None else None,
        user_id=order.user_id,
        wallet_id=wallet.id,
        gross_amount=gross,
        cash_amount=cash,
        promotional_amount=promotional,
        policy_version=policy_version,
        status=status,
        policy_snapshot=_snapshot(legacy_unknown=legacy_unknown),
    )
    db.add(allocation)
    db.flush()
    return allocation


def reserve_order_funding(
    order: Order,
    wallet: Wallet,
    amount: Decimal,
    db: Session,
) -> OrderFundingAllocation:
    """Freeze a new order and persist its immutable source split."""

    gross = funding_amount(amount)
    existing = _existing(db, "order", order.id)
    if existing:
        return existing
    assert_wallet_funding_invariants(wallet, db)
    if funding_amount(spendable_wallet_balance(wallet, db)) < gross:
        raise BizError("余额不足")
    promotional = min(funding_amount(wallet.promotional_balance), gross)
    wallet.balance = funding_amount(wallet.balance) - gross
    wallet.frozen = funding_amount(wallet.frozen) + gross
    wallet.promotional_balance = funding_amount(wallet.promotional_balance) - promotional
    wallet.promotional_frozen = funding_amount(wallet.promotional_frozen) + promotional
    allocation = _new_allocation(
        db,
        order=order,
        renewal=None,
        wallet=wallet,
        gross=gross,
        promotional=promotional,
        status="frozen",
    )
    assert_wallet_funding_invariants(wallet, db)
    return allocation


def _legacy_frozen_allocation(
    order: Order,
    wallet: Wallet,
    db: Session,
) -> OrderFundingAllocation:
    """Classify an unallocated historical reservation as fully promotional.

    Historical frozen funds cannot be reconstructed. Treating all of them as
    promotional is conservative: it can only reduce future commission, never
    turn an unknown/reward-funded debit into cash-backed consumption.
    """

    gross = funding_amount(order.amount)
    frozen = funding_amount(wallet.frozen)
    promotional_frozen = funding_amount(wallet.promotional_frozen)
    if frozen < gross:
        raise BizError("订单冻结余额异常，请联系平台服务人员核查", status_code=409)
    assigned_promotional = db.query(
        func.coalesce(func.sum(OrderFundingAllocation.promotional_amount), 0)
    ).filter(
        OrderFundingAllocation.wallet_id == wallet.id,
        OrderFundingAllocation.status == "frozen",
    ).scalar()
    assigned_promotional = funding_amount(assigned_promotional)
    available_preclassified = max(Decimal("0.000000"), promotional_frozen - assigned_promotional)
    unclassified = frozen - promotional_frozen
    needed_from_unclassified = max(Decimal("0.000000"), gross - available_preclassified)
    if needed_from_unclassified > unclassified:
        raise BizError("历史订单资金来源冲突，请联系平台服务人员核查", status_code=409)
    # init_db conservatively marks all historical frozen funds promotional. In
    # unit/legacy databases that have not run that migration, claim only the
    # still-unclassified remainder. Multiple old orders consume this pool in a
    # deterministic sequence without double classification.
    wallet.promotional_frozen = promotional_frozen + needed_from_unclassified
    return _new_allocation(
        db,
        order=order,
        renewal=None,
        wallet=wallet,
        gross=gross,
        promotional=gross,
        status="frozen",
        policy_version=LEGACY_UNKNOWN_FUNDING_POLICY_VERSION,
        legacy_unknown=True,
    )


def capture_order_funding(
    order: Order,
    wallet: Wallet,
    db: Session,
    *,
    captured_at: datetime | None = None,
) -> OrderFundingAllocation:
    allocation = _existing(db, "order", order.id)
    if allocation is None:
        allocation = _legacy_frozen_allocation(order, wallet, db)
    if allocation.status == "captured":
        return allocation
    if allocation.status != "frozen":
        raise BizError("订单资金状态异常，请联系平台服务人员核查", status_code=409)
    gross = funding_amount(allocation.gross_amount)
    promotional = funding_amount(allocation.promotional_amount)
    if funding_amount(wallet.frozen) < gross or funding_amount(wallet.promotional_frozen) < promotional:
        raise BizError("订单冻结余额异常，请联系平台服务人员核查", status_code=409)
    wallet.frozen = funding_amount(wallet.frozen) - gross
    wallet.promotional_frozen = funding_amount(wallet.promotional_frozen) - promotional
    allocation.status = "captured"
    allocation.captured_at = captured_at or datetime.now(timezone.utc)
    assert_wallet_funding_invariants(wallet, db)
    return allocation


def refund_order_funding(
    order: Order,
    wallet: Wallet,
    db: Session,
    *,
    refunded_at: datetime | None = None,
) -> OrderFundingAllocation:
    allocation = _existing(db, "order", order.id)
    if allocation is None:
        allocation = _legacy_frozen_allocation(order, wallet, db)
    if allocation.status == "refunded":
        return allocation
    if allocation.status != "frozen":
        raise BizError("订单资金状态异常，请联系平台服务人员核查", status_code=409)
    gross = funding_amount(allocation.gross_amount)
    promotional = funding_amount(allocation.promotional_amount)
    if funding_amount(wallet.frozen) < gross or funding_amount(wallet.promotional_frozen) < promotional:
        raise BizError("订单冻结余额异常，请联系平台服务人员核查", status_code=409)
    wallet.balance = funding_amount(wallet.balance) + gross
    wallet.frozen = funding_amount(wallet.frozen) - gross
    wallet.promotional_balance = funding_amount(wallet.promotional_balance) + promotional
    wallet.promotional_frozen = funding_amount(wallet.promotional_frozen) - promotional
    allocation.status = "refunded"
    allocation.refunded_at = refunded_at or datetime.now(timezone.utc)
    assert_wallet_funding_invariants(wallet, db)
    return allocation


def spend_renewal_funding(
    order: Order,
    renewal: OrderRenewal,
    wallet: Wallet,
    amount: Decimal,
    db: Session,
    *,
    captured_at: datetime | None = None,
) -> OrderFundingAllocation:
    gross = funding_amount(amount)
    existing = _existing(db, "renewal", renewal.id)
    if existing:
        return existing
    assert_wallet_funding_invariants(wallet, db)
    if funding_amount(spendable_wallet_balance(wallet, db)) < gross:
        raise BizError("余额不足")
    promotional = min(funding_amount(wallet.promotional_balance), gross)
    wallet.balance = funding_amount(wallet.balance) - gross
    wallet.promotional_balance = funding_amount(wallet.promotional_balance) - promotional
    allocation = _new_allocation(
        db,
        order=order,
        renewal=renewal,
        wallet=wallet,
        gross=gross,
        promotional=promotional,
        status="captured",
    )
    allocation.captured_at = captured_at or datetime.now(timezone.utc)
    assert_wallet_funding_invariants(wallet, db)
    return allocation


def cash_backed_amount(
    db: Session,
    *,
    source_type: str,
    source_id: int,
) -> Decimal:
    allocation = db.query(OrderFundingAllocation).filter(
        OrderFundingAllocation.source_type == source_type,
        OrderFundingAllocation.source_id == source_id,
        OrderFundingAllocation.status == "captured",
    ).first()
    # Historical events have no trustworthy source split and are deliberately
    # ineligible rather than inferred from the current wallet balance.
    return funding_amount(allocation.cash_amount) if allocation else Decimal("0.000000")
