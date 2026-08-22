"""订单/资产到期处理：到达 end_at 后自动转为 done/expired，配合收益结算停止。"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.asset import Asset
from app.models.order import Order
from app.services.qixiangpay import expire_pending_payment_orders


def expire_due():
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        orders = db.query(Order).filter(
            Order.status == "running",
            Order.end_at.isnot(None),
            Order.end_at < now,
        ).all()
        for o in orders:
            o.status = "done"
            o.last_modified_platform = "system"

        assets = db.query(Asset).filter(
            Asset.status == "active",
            Asset.end_at.isnot(None),
            Asset.end_at < now,
        ).all()
        for a in assets:
            a.status = "expired"

        payment_orders = expire_pending_payment_orders(db, now=now.replace(tzinfo=None))
        db.commit()
        if orders or assets or payment_orders:
            print(
                f"[lifecycle] 到期: {len(orders)} 订单, {len(assets)} 资产, "
                f"{payment_orders} 充值订单"
            )
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"[lifecycle] error: {e}")
    finally:
        db.close()
