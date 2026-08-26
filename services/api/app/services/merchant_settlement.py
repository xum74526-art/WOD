"""Idempotent merchant sale settlement backed by an auditable fact row."""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ledger import Ledger
from app.models.merchant_settlement import MerchantSettlement
from app.models.order import Order
from app.models.order_renewal import OrderRenewal
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.wallet import Wallet


MERCHANT_SETTLEMENT_POLICY_VERSION = "merchant-sale-v1"
CARD_HOUR_QUANTUM = Decimal("0.000001")


class MerchantSettlementError(RuntimeError):
    pass


def settlement_money(value: Decimal | float | int | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(CARD_HOUR_QUANTUM, rounding=ROUND_HALF_UP)


def merchant_service_fee_bps() -> int:
    value = int(settings.MERCHANT_SERVICE_FEE_BPS)
    if not 0 <= value <= 10_000:
        raise MerchantSettlementError("MERCHANT_SERVICE_FEE_BPS must be between 0 and 10000")
    return value


def assert_merchant_settlement_configuration_safe() -> None:
    """Fail application startup before an invalid policy can freeze orders."""

    merchant_service_fee_bps()
    for name in (
        "ORDER_DELIVERY_TIMEOUT_HOURS",
        "ORDER_CONFIRMATION_TIMEOUT_HOURS",
        "ORDER_DISPUTE_REVIEW_TIMEOUT_HOURS",
    ):
        if int(getattr(settings, name)) <= 0:
            raise MerchantSettlementError(f"{name} must be greater than zero")


def settle_merchant_sale(
    order: Order,
    db: Session,
    *,
    renewal: OrderRenewal | None = None,
    settled_at: datetime | None = None,
) -> MerchantSettlement | None:
    """Settle one confirmed WOD merchant sale exactly once.

    Merchant sale proceeds are real withdrawable earnings. Consumer, supplier,
    and invite rewards are deliberately handled elsewhere and only increase the
    non-withdrawable in-app balance.
    """

    product = db.query(Product).filter(Product.id == order.product_id).first()
    if product is None or product.supplier_id is None:
        return None
    supplier = db.query(Supplier).filter(Supplier.id == product.supplier_id).first()
    if supplier is None or int(supplier.user_id) == int(order.user_id):
        raise MerchantSettlementError("merchant settlement supplier is invalid")

    source_type = "renewal" if renewal is not None else "order"
    source_id = int(renewal.id if renewal is not None else order.id)
    event_key = f"merchant_settlement:{source_type}:{source_id}"
    existing = db.query(MerchantSettlement).filter(
        MerchantSettlement.event_key == event_key,
    ).first()
    if existing is not None:
        return existing

    gross = settlement_money(renewal.amount if renewal is not None else order.amount)
    if gross <= 0:
        raise MerchantSettlementError("merchant settlement gross amount must be positive")
    fee_bps = merchant_service_fee_bps()
    fee = settlement_money(gross * Decimal(fee_bps) / Decimal("10000"))
    net = settlement_money(gross - fee)
    now = settled_at or datetime.now(timezone.utc)

    wallet = db.query(Wallet).filter(
        Wallet.user_id == supplier.user_id,
    ).with_for_update().first()
    if wallet is None:
        raise MerchantSettlementError("merchant settlement wallet is missing")

    settlement = MerchantSettlement(
        event_key=event_key,
        policy_version=MERCHANT_SETTLEMENT_POLICY_VERSION,
        source_type=source_type,
        source_id=source_id,
        order_id=order.id,
        order_renewal_id=renewal.id if renewal is not None else None,
        buyer_user_id=order.user_id,
        supplier_id=supplier.id,
        supplier_user_id=supplier.user_id,
        wallet_id=wallet.id,
        gross_amount=gross,
        service_fee_bps=fee_bps,
        service_fee_amount=fee,
        net_amount=net,
        policy_snapshot={
            "policy_version": MERCHANT_SETTLEMENT_POLICY_VERSION,
            "service_fee_bps": fee_bps,
            "gross_equals_fee_plus_net": True,
            "merchant_income_withdrawable": True,
            "reward_card_hours_withdrawable": False,
        },
        status="settled",
        settled_at=now,
    )
    db.add(settlement)
    db.flush()  # claim the unique business event before mutating the wallet

    wallet.balance = settlement_money(wallet.balance) + net
    wallet.withdrawable_balance = settlement_money(wallet.withdrawable_balance) + net
    ledger = Ledger(
        user_id=supplier.user_id,
        wallet_id=wallet.id,
        type="merchant_sale_income",
        direction="in",
        amount=net,
        balance_after=settlement_money(wallet.balance),
        ref_order_id=order.id if renewal is None else None,
        ref_merchant_settlement_id=settlement.id,
        event_key=event_key,
        remark=(
            f"商家成交结算 {order.order_no}"
            if renewal is None
            else f"商家续费结算 {order.order_no} / 续费#{renewal.id}"
        ),
    )
    db.add(ledger)
    db.flush()
    settlement.ledger_id = ledger.id
    return settlement
