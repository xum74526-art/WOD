from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ledger import Ledger


# Every pre-accrual reward type is historical-only.  The ``test_*`` variants
# were written by the retired closed-test mode; the unprefixed variants were
# written by the retired live writer.  Neither family has a versioned,
# auditable entitlement row, so neither may become spendable when the current
# programs are enabled.
LEGACY_REWARD_TYPES = (
    "rebate",
    "supplier_rebate",
    "invite_reward",
    "test_rebate",
    "test_supplier",
    "test_invite",
)


def historical_synthetic_revenue(user_id: int, db: Session) -> Decimal:
    amount = db.query(func.coalesce(func.sum(Ledger.amount), 0)).filter(
        Ledger.user_id == user_id,
        Ledger.type == "revenue",
        Ledger.direction == "in",
    ).scalar()
    return Decimal(str(amount or 0))


def historical_synthetic_rewards(user_id: int, db: Session) -> Decimal:
    amount = db.query(func.coalesce(func.sum(Ledger.amount), 0)).filter(
        Ledger.user_id == user_id,
        Ledger.type.in_(LEGACY_REWARD_TYPES),
        Ledger.direction == "in",
    ).scalar()
    return Decimal(str(amount or 0))


def spendable_wallet_balance(wallet, db: Session) -> Decimal:
    """Return CNY account balance available for in-app purchases only.

    Withdrawable earnings are a separate reserved bucket: they may be paid out
    or unfrozen, but never consumed by an order.  Keeping ``W <= B`` means all
    existing order/refund code remains safe after checking this value.
    """
    balance = Decimal(str(wallet.balance or 0))
    excluded = Decimal("0")
    if not settings.REVENUE_SETTLEMENT_ENABLED:
        excluded += historical_synthetic_revenue(wallet.user_id, db)
    # Old reward types predate auditable accruals. They remain excluded even
    # when a new independent program is enabled; otherwise a feature toggle
    # could silently reactivate historical synthetic balances.
    excluded += historical_synthetic_rewards(wallet.user_id, db)
    withdrawable = Decimal(str(wallet.withdrawable_balance or 0))
    return max(Decimal("0"), balance - excluded - withdrawable)
