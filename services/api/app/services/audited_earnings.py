"""Read-only personal earnings projection from auditable business facts.

The retired ``revenues`` table was populated by a fixed-rate simulator and is
therefore never mixed into current earnings.  Personal earnings are derived
only from settled consumer purchase rebates and settled holding-asset sales.
Active holding P/L is shown separately because it is still unrealised.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.asset import Asset
from app.models.holding_asset_sale import HoldingAssetSale
from app.models.revenue import Revenue
from app.models.reward_accrual import RewardAccrual
from app.services.holding_trade import holding_asset_quote
from app.services.reward_program import PROGRAM_CONSUMER


MONEY_QUANTUM = Decimal("0.001")


def _money(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _business_timezone():
    try:
        return ZoneInfo(settings.REWARD_TIMEZONE)
    except ZoneInfoNotFoundError:
        return timezone.utc


def _business_today() -> date:
    return datetime.now(timezone.utc).astimezone(_business_timezone()).date()


def _business_date(value: datetime) -> date:
    current = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return current.astimezone(_business_timezone()).date()


def _utc_naive_bounds(start: date, days: int) -> tuple[datetime, datetime]:
    zone = _business_timezone()
    local_start = datetime.combine(start, time.min, tzinfo=zone)
    local_end = local_start + timedelta(days=days)
    return (
        local_start.astimezone(timezone.utc).replace(tzinfo=None),
        local_end.astimezone(timezone.utc).replace(tzinfo=None),
    )


def _consumer_reward_total(user_id: int, db: Session, *, start: datetime | None = None, end: datetime | None = None) -> Decimal:
    query = db.query(func.coalesce(func.sum(RewardAccrual.reward_amount), 0)).filter(
        RewardAccrual.beneficiary_user_id == user_id,
        RewardAccrual.program_code == PROGRAM_CONSUMER,
        RewardAccrual.status == "settled",
        RewardAccrual.settled_at.is_not(None),
    )
    if start is not None:
        query = query.filter(RewardAccrual.settled_at >= start)
    if end is not None:
        query = query.filter(RewardAccrual.settled_at < end)
    return _money(query.scalar())


def _holding_sale_pnl_total(user_id: int, db: Session, *, start: datetime | None = None, end: datetime | None = None) -> Decimal:
    query = db.query(func.coalesce(func.sum(HoldingAssetSale.pnl_card_hours), 0)).filter(
        HoldingAssetSale.user_id == user_id,
    )
    if start is not None:
        query = query.filter(HoldingAssetSale.settled_at >= start)
    if end is not None:
        query = query.filter(HoldingAssetSale.settled_at < end)
    return _money(query.scalar())


def audited_earnings_summary(user_id: int, db: Session) -> dict:
    today = _business_today()
    start, end = _utc_naive_bounds(today, 1)
    settled_rebate_total = _consumer_reward_total(user_id, db)
    settled_rebate_today = _consumer_reward_total(user_id, db, start=start, end=end)
    realised_holding_pnl = _holding_sale_pnl_total(user_id, db)
    realised_holding_pnl_today = _holding_sale_pnl_total(user_id, db, start=start, end=end)
    pending_rebate = _money(db.query(func.coalesce(func.sum(RewardAccrual.reward_amount), 0)).filter(
        RewardAccrual.beneficiary_user_id == user_id,
        RewardAccrual.program_code == PROGRAM_CONSUMER,
        RewardAccrual.status == "pending",
    ).scalar())

    active_holdings = db.query(Asset).filter(
        Asset.user_id == user_id,
        Asset.purchase_type == "holding",
        Asset.status == "active",
    ).all()
    unrealised_holding_pnl = Decimal("0")
    priced_buy_value = Decimal("0")
    priced_assets = 0
    for asset in active_holdings:
        quote = holding_asset_quote(asset, db)
        if quote.get("pnl") is None or quote.get("buy_price") is None:
            continue
        unrealised_holding_pnl += Decimal(str(quote["pnl"]))
        priced_buy_value += Decimal(str(quote["buy_price"]))
        priced_assets += 1

    legacy_total = _money(db.query(func.coalesce(func.sum(Revenue.amount), 0)).filter(
        Revenue.user_id == user_id,
    ).scalar())
    unrealised_holding_pnl = _money(unrealised_holding_pnl)
    unrealised_rate = (
        (unrealised_holding_pnl / priced_buy_value * Decimal("100")).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        if priced_buy_value > 0 else Decimal("0")
    )
    return {
        # Compatibility fields now represent real, realised personal earnings.
        "today": float(_money(settled_rebate_today + realised_holding_pnl_today)),
        "total": float(_money(settled_rebate_total + realised_holding_pnl)),
        "rate": float(unrealised_rate),
        "settled_rebate_total": float(settled_rebate_total),
        "settled_rebate_today": float(settled_rebate_today),
        "pending_rebate": float(pending_rebate),
        "holding_realized_pnl": float(realised_holding_pnl),
        "holding_realized_pnl_today": float(realised_holding_pnl_today),
        "holding_unrealized_pnl": float(unrealised_holding_pnl),
        "holding_unrealized_pnl_rate": float(unrealised_rate),
        "holding_active_assets": len(active_holdings),
        "holding_priced_assets": priced_assets,
        "audited_earnings_enabled": True,
        # Kept for old clients and for audit disclosure only. This switch and
        # total describe the retired simulator, not current earnings.
        "revenue_settlement_enabled": settings.REVENUE_SETTLEMENT_ENABLED,
        "historical_test_total": float(legacy_total),
    }


def audited_earnings_chart(user_id: int, range_days: int, db: Session) -> list[dict]:
    end_date = _business_today() + timedelta(days=1)
    start_date = end_date - timedelta(days=range_days)
    start, end = _utc_naive_bounds(start_date, range_days)
    daily: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))

    rewards = db.query(RewardAccrual).filter(
        RewardAccrual.beneficiary_user_id == user_id,
        RewardAccrual.program_code == PROGRAM_CONSUMER,
        RewardAccrual.status == "settled",
        RewardAccrual.settled_at >= start,
        RewardAccrual.settled_at < end,
    ).all()
    for reward in rewards:
        if reward.settled_at is not None:
            daily[_business_date(reward.settled_at)] += Decimal(str(reward.reward_amount or 0))

    sales = db.query(HoldingAssetSale).filter(
        HoldingAssetSale.user_id == user_id,
        HoldingAssetSale.settled_at >= start,
        HoldingAssetSale.settled_at < end,
    ).all()
    for sale in sales:
        daily[_business_date(sale.settled_at)] += Decimal(str(sale.pnl_card_hours or 0))

    cumulative = Decimal("0")
    points = []
    for offset in range(range_days):
        current = start_date + timedelta(days=offset)
        cumulative = _money(cumulative + daily[current])
        points.append({"date": current.strftime("%m-%d"), "amount": float(cumulative)})
    return points


def audited_earnings_records(user_id: int, db: Session, limit: int = 50) -> list[dict]:
    rewards = db.query(RewardAccrual).filter(
        RewardAccrual.beneficiary_user_id == user_id,
        RewardAccrual.program_code == PROGRAM_CONSUMER,
        RewardAccrual.status == "settled",
        RewardAccrual.settled_at.is_not(None),
    ).order_by(RewardAccrual.settled_at.desc(), RewardAccrual.id.desc()).limit(limit).all()
    sales = db.query(HoldingAssetSale).filter(
        HoldingAssetSale.user_id == user_id,
    ).order_by(HoldingAssetSale.settled_at.desc(), HoldingAssetSale.id.desc()).limit(limit).all()

    records = [
        {
            "id": reward.id,
            "record_key": f"consumer_rebate:{reward.id}",
            "source_type": "consumer_rebate",
            "asset_id": reward.asset_id,
            "amount": float(_money(reward.reward_amount)),
            "date": _business_date(reward.settled_at).isoformat(),
            "created_at": reward.settled_at.isoformat(),
        }
        for reward in rewards if reward.settled_at is not None
    ]
    records.extend({
        "id": sale.id,
        "record_key": f"holding_sale:{sale.id}",
        "source_type": "holding_sale",
        "asset_id": sale.asset_id,
        "amount": float(_money(sale.pnl_card_hours)),
        "date": _business_date(sale.settled_at).isoformat(),
        "created_at": sale.settled_at.isoformat(),
    } for sale in sales)
    records.sort(key=lambda item: item["created_at"], reverse=True)
    return records[:limit]
