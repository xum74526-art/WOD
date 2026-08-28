from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.asset import Asset
from app.models.ledger import Ledger
from app.models.product import Product
from app.models.revenue import Revenue
from app.models.user import User
from app.models.wallet import Wallet
from app.schemas.asset import AssetOut
from app.services.trade_mode import require_direct_trade_enabled
from app.services.wallet_balance import spendable_wallet_balance
from app.utils.response import BizError, success

router = APIRouter(prefix="/api/assets", tags=["asset"])


def _asset_out(a: Asset, db: Session) -> dict:
    p = db.query(Product).filter(Product.id == a.product_id).first()
    out = AssetOut.model_validate(a).model_dump()
    quantity = max(int(a.quantity or 1), 1)
    out["unit_value"] = float(a.value)
    out["value"] = round(float(a.value) * quantity, 4)
    out["product_name"] = p.name if p else None
    out["gpu_model"] = p.gpu_model if p else None
    today = date.today()
    today_rev = db.query(func.coalesce(func.sum(Revenue.amount), 0)).filter(
        Revenue.asset_id == a.id, Revenue.date == today
    ).scalar()
    total_rev = db.query(func.coalesce(func.sum(Revenue.amount), 0)).filter(
        Revenue.asset_id == a.id
    ).scalar()
    out["historical_test_revenue"] = round(float(total_rev), 4)
    out["revenue_settlement_enabled"] = settings.REVENUE_SETTLEMENT_ENABLED
    from app.services.reward_program import PROGRAM_CONSUMER, program_enabled
    out["reward_service_enabled"] = program_enabled(PROGRAM_CONSUMER)
    out["today_revenue"] = round(float(today_rev), 4) if settings.REVENUE_SETTLEMENT_ENABLED else 0
    out["accumulated_revenue"] = round(float(total_rev), 4) if settings.REVENUE_SETTLEMENT_ENABLED else 0
    if a.end_at and a.status == "active":
        end = a.end_at.replace(tzinfo=timezone.utc) if a.end_at.tzinfo is None else a.end_at
        out["remaining_days"] = max(0, (end - datetime.now(timezone.utc)).days)
    else:
        out["remaining_days"] = 0 if a.status != "active" else None
    return out


@router.get("")
def my_assets(
    status_filter: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Asset).filter(Asset.user_id == user.id)
    if status_filter:
        q = q.filter(Asset.status == status_filter)
    else:
        q = q.filter(Asset.status == "active")
    items = q.order_by(Asset.created_at.desc()).all()
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
    total_value = sum(float(a.value) * a.quantity for a in items)
    wallet_balance = float(spendable_wallet_balance(wallet, db)) if wallet else 0
    today = date.today()
    today_total = db.query(func.coalesce(func.sum(Revenue.amount), 0)).filter(
        Revenue.user_id == user.id, Revenue.date == today
    ).scalar()
    rate = round(float(today_total) / total_value * 100, 2) if settings.REVENUE_SETTLEMENT_ENABLED and total_value > 0 else 0
    out_items = [_asset_out(item, db) for item in items]
    return success({
        "total_value": round(total_value, 2),
        "wallet_balance": round(wallet_balance, 2),
        "pending_revenue": 0,
        "revenue_rate": rate,
        "revenue_settlement_enabled": settings.REVENUE_SETTLEMENT_ENABLED,
        "historical_test_revenue": round(sum(float(item.get("historical_test_revenue", 0)) for item in out_items), 2),
        "items": out_items,
    })


@router.get("/{aid}")
def asset_detail(aid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.id == aid, Asset.user_id == user.id).first()
    if not a:
        raise BizError("资产不存在", status_code=404)
    out = _asset_out(a, db)
    # 历史持有资产保留展示，但在真实产权/二级市场接入前不生成模拟估值。
    if a.purchase_type == "holding" and a.status == "active":
        out["current_price"] = None
        out["pnl"] = None
        out["pnl_pct"] = None
        out["can_sell"] = False
        out["trading_unavailable_reason"] = "持有交易与二级市场尚未接入"
    # Legacy asset flags remain visible only as historical audit data. Current
    # rewards are derived exclusively from versioned accrual rows.
    out["historical_test_reward"] = a.rebate_amount if a.rebate_status == "rewarded" else 0
    from app.services.reward_entitlements import get_asset_consumer_reward, get_consumer_summary
    reward = get_asset_consumer_reward(a.id, db)
    out["rebate_status"] = reward["rebate_status"] if reward else None
    out["rebate_amount"] = reward["rebate_amount"] if reward else None
    if reward:
        out["rebate_info"] = {**get_consumer_summary(a.user_id, db), **reward}
    return success(out)


@router.post("/{aid}/sell")
def sell_asset(aid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_direct_trade_enabled()
    a = db.query(Asset).filter(Asset.id == aid, Asset.user_id == user.id).first()
    if not a:
        raise BizError("资产不存在", status_code=404)
    if a.status != "active":
        raise BizError("该资产不可出售")
    if a.purchase_type != "holding":
        raise BizError("使用模式资产不可出售")
    raise BizError("持有交易与二级市场尚未接入，当前不可出售", status_code=503)
