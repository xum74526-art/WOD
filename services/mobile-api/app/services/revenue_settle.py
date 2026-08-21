"""收益结算：每 INTERVAL 秒为未到期活跃资产产生收益，Decimal 全链路，写 ledger。

幂等：MVP 单进程内按 tick 自然分摊，避免重复入账；多实例部署需引入分布式锁。
"""
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.asset import Asset
from app.models.ledger import Ledger
from app.models.revenue import Revenue
from app.models.wallet import Wallet

INTERVAL_SECONDS = 30
TICKS_PER_DAY = 24 * 3600 // INTERVAL_SECONDS  # = 2880


def _q(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def settle_revenue():
    if not settings.REVENUE_SETTLEMENT_ENABLED:
        return
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        # 只结算未到期的活跃资产
        assets = db.query(Asset).filter(
            Asset.status == "active",
            (Asset.end_at.is_(None)) | (Asset.end_at > now),
        ).all()
        if not assets:
            return
        today = date.today()
        for a in assets:
            value = Decimal(str(a.value)) * Decimal(str(a.quantity))
            daily_income = value * Decimal(str(a.daily_rate))
            tick_income = daily_income / Decimal(TICKS_PER_DAY)
            if tick_income <= 0:
                continue
            amt = _q(tick_income)
            db.add(Revenue(asset_id=a.id, user_id=a.user_id, amount=amt, date=today))
            w = db.query(Wallet).filter(Wallet.user_id == a.user_id).first()
            if w:
                w.balance = w.balance + amt
                # This path is globally disabled until metered, auditable
                # compute settlement is connected. Once explicitly enabled,
                # new (not historical) settled revenue is withdrawable but is
                # excluded from in-app purchasing by spendable_wallet_balance.
                w.withdrawable_balance = w.withdrawable_balance + amt
                db.add(Ledger(
                    user_id=a.user_id, wallet_id=w.id, type="revenue", direction="in",
                    amount=amt, balance_after=w.balance, remark=f"算力收益 #{a.id}",
                ))
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"[settle_revenue] error: {e}")
    finally:
        db.close()
