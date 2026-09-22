from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.asset import Asset
from app.models.holding_asset_sale import HoldingAssetSale
from app.models.ledger import Ledger
from app.models.product import Product
from app.models.revenue import Revenue
from app.models.user import User
from app.models.wallet import Wallet
from app.schemas.asset import AssetOut, AssetSellIn
from app.services.holding_trade import holding_asset_quote, settle_holding_asset_sale
from app.services.trade_mode import require_holding_trade_enabled
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
    out["audited_earnings_enabled"] = True
    from app.services.reward_program import PROGRAM_CONSUMER, program_enabled
    out["reward_service_enabled"] = program_enabled(PROGRAM_CONSUMER)
    out["today_revenue"] = round(float(today_rev), 4) if settings.REVENUE_SETTLEMENT_ENABLED else 0
    out["accumulated_revenue"] = round(float(total_rev), 4) if settings.REVENUE_SETTLEMENT_ENABLED else 0
    if a.end_at and a.status == "active":
        end = a.end_at.replace(tzinfo=timezone.utc) if a.end_at.tzinfo is None else a.end_at
        out["remaining_days"] = max(0, (end - datetime.now(timezone.utc)).days)
    else:
        out["remaining_days"] = 0 if a.status != "active" else None
    if a.purchase_type == "holding":
        out.update(holding_asset_quote(a, db))
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
    wallet_balance = float(spendable_wallet_balance(wallet, db)) if wallet else 0
    today = date.today()
    today_total = db.query(func.coalesce(func.sum(Revenue.amount), 0)).filter(
        Revenue.user_id == user.id, Revenue.date == today
    ).scalar()
    out_items = [_asset_out(item, db) for item in items]
    from app.services.reward_entitlements import get_consumer_summary
    consumer_reward = get_consumer_summary(user.id, db)
    total_value = sum(
        float(item.get("current_price"))
        if item.get("purchase_type") == "holding" and item.get("current_price") is not None
        else float(item.get("value") or 0)
        for item in out_items
    )
    rate = round(float(today_total) / total_value * 100, 2) if settings.REVENUE_SETTLEMENT_ENABLED and total_value > 0 else 0
    return success({
        "total_value": round(total_value, 2),
        "wallet_balance": round(wallet_balance, 2),
        # Compatibility name retained for existing clients. The value is the
        # user's real pending purchase rebate, never simulated daily revenue.
        "pending_revenue": round(float(consumer_reward["pending_rebate"]), 2),
        "revenue_rate": rate,
        "audited_earnings_enabled": True,
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
def sell_asset(
    aid: int,
    data: AssetSellIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_holding_trade_enabled()
    if db.get_bind().dialect.name == "sqlite":
        if db.in_transaction():
            db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    try:
        payload = settle_holding_asset_sale(
            asset_id=aid,
            user_id=user.id,
            client_request_id=data.client_request_id,
            expected_unit_price_card_hours=data.expected_unit_price_card_hours,
            db=db,
        )
        db.commit()
        return success(payload)
    except BizError:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        existing = db.query(HoldingAssetSale).filter(
            HoldingAssetSale.asset_id == aid,
            HoldingAssetSale.user_id == user.id,
        ).first()
        if existing is not None:
            return success({
                "id": existing.asset_id,
                "asset_id": existing.asset_id,
                "status": "sold",
                "sell_price": float(existing.sell_value_card_hours),
                "buy_price": float(existing.buy_value_card_hours),
                "pnl": float(existing.pnl_card_hours),
                "current_unit_price": float(existing.unit_price_card_hours_per_gpu_hour),
                "price_observed_at": existing.price_observed_at,
                "settled_at": existing.settled_at,
            })
        raise BizError("出售失败，请刷新后重试", status_code=409)
    except Exception:
        db.rollback()
        raise BizError("出售失败，请刷新后重试", status_code=409)
