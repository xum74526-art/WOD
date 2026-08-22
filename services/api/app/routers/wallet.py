from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.sensitive import last_four, sensitive_capability_enabled
from app.db.session import get_db
from app.models.bank_card import BankCard
from app.models.ledger import Ledger
from app.models.revenue import Revenue
from app.models.user import User
from app.models.wallet import Wallet
from app.schemas.wallet import LedgerOut, RechargeIn, WithdrawIn
from app.services.payment_gateway import provider_configured, public_config as payment_public_config
from app.utils.response import BizError, success
from app.services.wallet_balance import (
    LEGACY_REWARD_TYPES,
    historical_synthetic_revenue,
    historical_synthetic_rewards,
    spendable_wallet_balance,
)
from app.services.reward_program import (
    REWARD_MODE_CLOSED_TEST,
    ledger_filter_types,
    public_reward_type,
    reward_mode,
    reward_program_enabled,
)

router = APIRouter(prefix="/api/wallet", tags=["wallet"])


def _get_wallet(user: User, db: Session) -> Wallet:
    w = db.query(Wallet).filter(Wallet.user_id == user.id).first()
    if not w:
        raise BizError("钱包不存在", status_code=404)
    return w


@router.get("")
def wallet_info(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    w = _get_wallet(user, db)
    total_income = db.query(func.coalesce(func.sum(Revenue.amount), 0)).filter(
        Revenue.user_id == user.id
    ).scalar()
    historical_income = historical_synthetic_revenue(user.id, db)
    historical_rewards = historical_synthetic_rewards(user.id, db)
    # 查是否有绑定的银行卡
    has_bank_card = db.query(BankCard).filter(BankCard.user_id == user.id).count() > 0
    return success({
        "balance": float(spendable_wallet_balance(w, db)),
        "total_available_balance": float(w.balance or 0),
        "frozen": float(w.frozen),
        "withdrawable_balance": float(w.withdrawable_balance or 0),
        "withdraw_frozen": float(w.withdraw_frozen or 0),
        "total_income": round(float(total_income), 2) if settings.REVENUE_SETTLEMENT_ENABLED else 0,
        "historical_test_revenue": round(float(historical_income), 2),
        "historical_test_rewards": round(float(historical_rewards), 2),
        "revenue_settlement_enabled": settings.REVENUE_SETTLEMENT_ENABLED,
        "reward_service_enabled": reward_program_enabled(),
        "reward_mode": reward_mode(),
        "has_bank_card": has_bank_card,
        # Kept for old clients; it now means recharge collection only.
        "payment_service_enabled": provider_configured(),
        "recharge_service_enabled": provider_configured(),
        "withdraw_service_enabled": sensitive_capability_enabled(settings.MANUAL_PAYOUT_ENABLED),
        "payment_config": payment_public_config(),
    })


@router.post("/recharge")
def recharge(data: RechargeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # This legacy endpoint used to mutate the wallet immediately.  Keeping it
    # as an explicit non-mutating error prevents an old App build from bypassing
    # provider payment, signature verification, and idempotent notification.
    raise BizError("请更新客户端并通过码支付收银台完成充值", status_code=410)


class WithdrawInV2(BaseModel):
    amount: float
    bank_card_id: int


@router.post("/withdraw")
def withdraw(data: WithdrawInV2, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Old clients used this route for a fake immediate payout.  It is kept only
    # as a non-mutating tombstone so no stale APK can bypass review, freezing,
    # receipt evidence, or the independent finance allow-list.
    raise BizError(
        "封闭测试卡时不能通过旧版即时提现；请更新客户端后提交人工审核申请",
        status_code=410,
    )


@router.get("/ledger")
def ledger_list(
    type_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Ledger).filter(Ledger.user_id == user.id)
    if type_filter:
        reward_types = ledger_filter_types(type_filter)
        q = q.filter(Ledger.type.in_(reward_types)) if reward_types else q.filter(Ledger.type == type_filter)
    total = q.count()
    items = q.order_by(Ledger.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    output_items = []
    for item in items:
        output = LedgerOut.model_validate(item).model_dump()
        output["type"] = public_reward_type(output["type"])
        if not settings.REVENUE_SETTLEMENT_ENABLED and output["type"] == "revenue":
            output["type"] = "test_revenue"
            output["remark"] = "历史测试收益（不计入当前可用余额）"
        elif not settings.REWARD_SERVICE_ENABLED and output["type"] in LEGACY_REWARD_TYPES and item.type in LEGACY_REWARD_TYPES:
            output["type"] = "test_reward"
            output["remark"] = "历史测试奖励（不计入当前可用余额或权益）"
        output_items.append(output)
    return success({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": output_items,
    })
