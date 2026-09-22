from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.asset import Asset
from app.models.holding_asset_sale import HoldingAssetSale
from app.models.ledger import Ledger
from app.models.market_price import MarketSourceStatus
from app.models.order import Order
from app.models.order_funding import OrderFundingAllocation
from app.models.product import Product
from app.models.wallet import Wallet
from app.services.funding_allocation import assert_wallet_funding_invariants, funding_amount
from app.services.market_freshness import product_market_source, product_market_state, source_state
from app.services.market_sync import utcnow
from app.services.trade_mode import holding_trade_enabled
from app.services.wallet_balance import spendable_wallet_balance
from app.utils.response import BizError


HOLDING_LIFECYCLE_POLICY = "holding-buyback-v1"
HOLDING_SALE_POLICY = "holding-buyback-settlement-v1"
UNIT_PRICE_QUANTUM = Decimal("0.0001")
MONEY_SCALE = Decimal("0.000001")


def _amount(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_SCALE, rounding=ROUND_HALF_UP)


def _unit_price(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(UNIT_PRICE_QUANTUM, rounding=ROUND_HALF_UP)


def _sale_payload(sale: HoldingAssetSale) -> dict:
    return {
        "id": sale.asset_id,
        "asset_id": sale.asset_id,
        "status": "sold",
        "sell_price": float(sale.sell_value_card_hours),
        "current_price": float(sale.sell_value_card_hours),
        "current_unit_price": float(sale.unit_price_card_hours_per_gpu_hour),
        "buy_price": float(sale.buy_value_card_hours),
        "pnl": float(sale.pnl_card_hours),
        "cash_value": float(sale.cash_value_card_hours),
        "promotional_value": float(sale.promotional_value_card_hours),
        "price_observed_at": sale.price_observed_at,
        "settled_at": sale.settled_at,
        "client_request_id": sale.client_request_id,
    }


def holding_asset_quote(asset: Asset, db: Session) -> dict:
    """Return an auditable current buyback quote or an explicit refusal.

    Historical ``holding`` rows are display-only. Only assets created under the
    current lifecycle policy can ever enter platform buyback settlement.
    """

    recorded_sale = db.query(HoldingAssetSale).filter(
        HoldingAssetSale.asset_id == asset.id,
    ).first()
    if recorded_sale is not None:
        sell_value = _amount(recorded_sale.sell_value_card_hours)
        buy_value = _amount(recorded_sale.buy_value_card_hours)
        pnl = _amount(recorded_sale.pnl_card_hours)
        return {
            "current_price": float(sell_value),
            "current_unit_price": float(recorded_sale.unit_price_card_hours_per_gpu_hour),
            "buy_price": float(buy_value),
            "pnl": float(pnl),
            "pnl_pct": round(float(pnl / buy_value * 100), 2) if buy_value > 0 else 0,
            "price_observed_at": recorded_sale.price_observed_at,
            "can_sell": False,
            "trading_unavailable_reason": "该持有资产已出售",
        }

    base = {
        "current_price": None,
        "current_unit_price": None,
        "buy_price": float(_amount(Decimal(str(asset.value)) * Decimal(max(int(asset.quantity or 1), 1)))),
        "pnl": None,
        "pnl_pct": None,
        "price_observed_at": None,
        "can_sell": False,
        "trading_unavailable_reason": None,
    }
    if asset.purchase_type != "holding":
        base["trading_unavailable_reason"] = "使用模式资产不可出售"
        return base
    if asset.status != "active":
        base["trading_unavailable_reason"] = "该资产当前不可出售"
        return base
    if not holding_trade_enabled():
        base["trading_unavailable_reason"] = "持有交易服务暂未开放"
        return base

    order = db.query(Order).filter(Order.id == asset.order_id).first() if asset.order_id else None
    if (
        order is None
        or int(order.user_id) != int(asset.user_id)
        or int(order.product_id) != int(asset.product_id)
        or order.purchase_type != "holding"
        or order.status != "completed"
        or order.lifecycle_policy_version != HOLDING_LIFECYCLE_POLICY
        or not order.purchase_hours
    ):
        base["trading_unavailable_reason"] = "历史持有资产缺少可核验的买入记录，请联系平台核查"
        return base

    product = db.query(Product).filter(Product.id == asset.product_id).first()
    if (
        product is None
        or product.status != "on"
        or product_market_source(product) != "kai"
        or product.supplier_id is not None
    ):
        base["trading_unavailable_reason"] = "该资产不属于平台自营行情，暂不支持出售"
        return base

    now = utcnow()
    source_rows = db.query(MarketSourceStatus).filter(MarketSourceStatus.enabled.is_(True)).all()
    states = {row.source: source_state(row, now) for row in source_rows}
    if product_market_state(product, states, now, settings.PRODUCT_OFFER_MAX_AGE_SECONDS) != "live":
        base["trading_unavailable_reason"] = "当前行情已延迟或过期，请稍后刷新"
        return base

    rate = Decimal(str(settings.CARD_HOUR_RMB_RATE or 0))
    if rate <= 0 or Decimal(str(product.price or 0)) <= 0 or product.price_updated_at is None:
        base["trading_unavailable_reason"] = "当前报价配置无效，请联系平台核查"
        return base

    unit = _amount(Decimal(str(product.price)) / rate)
    quantity = max(int(asset.quantity or 1), 1)
    sell_value = _amount(unit * Decimal(int(order.purchase_hours)) * Decimal(quantity))
    buy_value = _amount(order.amount)
    pnl = _amount(sell_value - buy_value)
    return {
        "current_price": float(sell_value),
        "current_unit_price": float(unit),
        "buy_price": float(buy_value),
        "pnl": float(pnl),
        "pnl_pct": round(float(pnl / buy_value * 100), 2) if buy_value > 0 else 0,
        "price_observed_at": product.price_updated_at,
        "can_sell": True,
        "trading_unavailable_reason": None,
    }


def settle_holding_asset_sale(
    *,
    asset_id: int,
    user_id: int,
    client_request_id: str,
    expected_unit_price_card_hours: Decimal,
    db: Session,
) -> dict:
    existing_request = db.query(HoldingAssetSale).filter(
        HoldingAssetSale.user_id == user_id,
        HoldingAssetSale.client_request_id == client_request_id,
    ).with_for_update().first()
    if existing_request is not None:
        if int(existing_request.asset_id) != int(asset_id):
            raise BizError("重复请求编号已用于其他资产，请重新提交", status_code=409)
        return _sale_payload(existing_request)

    asset = db.query(Asset).filter(
        Asset.id == asset_id,
        Asset.user_id == user_id,
    ).with_for_update().first()
    if asset is None:
        raise BizError("资产不存在", status_code=404)

    existing_sale = db.query(HoldingAssetSale).filter(
        HoldingAssetSale.asset_id == asset.id,
    ).with_for_update().first()
    if existing_sale is not None:
        return _sale_payload(existing_sale)

    # Lock and refresh the quoted product before deriving the settlement
    # value. This closes the small race where an ingestion worker could update
    # the market price after the user confirmed it but before settlement.
    product = db.query(Product).filter(
        Product.id == asset.product_id,
    ).with_for_update().populate_existing().first()
    if product is None:
        raise BizError("资产对应的算力资源不存在", status_code=409)
    quote = holding_asset_quote(asset, db)
    if not quote["can_sell"]:
        raise BizError(quote["trading_unavailable_reason"] or "该资产当前不可出售", status_code=409)
    current_unit = _amount(quote["current_unit_price"])
    if _unit_price(expected_unit_price_card_hours) != _unit_price(current_unit):
        raise BizError("出售价格已更新，请刷新后重新确认", status_code=409)

    order = db.query(Order).filter(Order.id == asset.order_id).with_for_update().one()
    wallet = db.query(Wallet).filter(Wallet.user_id == user_id).with_for_update().first()
    if wallet is None:
        raise BizError("钱包不存在", status_code=404)
    allocation = db.query(OrderFundingAllocation).filter(
        OrderFundingAllocation.source_type == "order",
        OrderFundingAllocation.source_id == order.id,
        OrderFundingAllocation.status == "captured",
    ).with_for_update().first()
    if allocation is None or allocation.policy_version != "wallet-funding-v1":
        raise BizError("持有资产资金来源缺少可核验记录，请联系平台核查", status_code=409)

    assert_wallet_funding_invariants(wallet, db)
    buy_value = _amount(order.amount)
    sell_value = _amount(quote["current_price"])
    promotional_bought = _amount(allocation.promotional_amount)
    if buy_value <= 0 or promotional_bought < 0 or promotional_bought > buy_value:
        raise BizError("持有资产资金分层异常，请联系平台核查", status_code=409)
    if promotional_bought == 0:
        promotional_value = Decimal("0.000000")
    elif promotional_bought == buy_value:
        promotional_value = sell_value
    else:
        promotional_value = (
            sell_value * promotional_bought / buy_value
        ).quantize(MONEY_SCALE, rounding=ROUND_CEILING)
        promotional_value = min(promotional_value, sell_value)
    cash_value = _amount(sell_value - promotional_value)

    now = utcnow()
    sale = HoldingAssetSale(
        event_key=f"holding_asset_sale:{asset.id}",
        client_request_id=client_request_id,
        asset_id=asset.id,
        order_id=order.id,
        user_id=user_id,
        wallet_id=wallet.id,
        product_id=product.id,
        quantity=max(int(asset.quantity or 1), 1),
        purchase_hours=int(order.purchase_hours),
        market_source="kai",
        unit_price_cny_per_gpu_hour=_amount(product.price),
        unit_price_card_hours_per_gpu_hour=current_unit,
        buy_value_card_hours=buy_value,
        sell_value_card_hours=sell_value,
        pnl_card_hours=_amount(sell_value - buy_value),
        cash_value_card_hours=cash_value,
        promotional_value_card_hours=promotional_value,
        price_observed_at=product.price_updated_at,
        policy_version=HOLDING_SALE_POLICY,
        policy_snapshot={
            "counterparty": "kai_platform_card_hour_buyback",
            "settlement_currency": "card_hours",
            "withdrawable_credit": False,
            "quote_source": "kai",
            "promotional_classification": "preserve_original_ratio_round_up",
        },
        settled_at=now,
    )
    wallet.balance = funding_amount(wallet.balance) + sell_value
    wallet.promotional_balance = funding_amount(wallet.promotional_balance) + promotional_value
    asset.status = "sold"
    asset.sell_price = float(sell_value)
    restored_stock = max(int(product.stock or 0), 0) + max(int(asset.quantity or 1), 1)
    if product.platform_stock_cap is not None:
        restored_stock = min(restored_stock, max(int(product.platform_stock_cap), 0))
    product.stock = restored_stock
    db.add(sale)
    db.flush()
    db.add(Ledger(
        user_id=user_id,
        wallet_id=wallet.id,
        type="asset_sale",
        direction="in",
        amount=sell_value,
        balance_after=spendable_wallet_balance(wallet, db),
        ref_order_id=order.id,
        event_key=sale.event_key,
        remark=f"出售持有资产({order.order_no})，按 KAI 最新有效行情结算为卡时",
    ))
    assert_wallet_funding_invariants(wallet, db)
    db.flush()
    return _sale_payload(sale)
