from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import OrmModel


class WalletOut(BaseModel):
    balance: float
    frozen: float
    total_income: float = 0


class RechargeIn(BaseModel):
    amount: float


class WithdrawIn(BaseModel):
    amount: float


class LedgerOut(OrmModel):
    id: int
    type: str
    direction: str
    amount: float
    balance_after: float
    remark: str | None = None
    ref_order_id: int | None = None
    ref_payment_order_id: int | None = None
    ref_order_renewal_id: int | None = None
    ref_reward_accrual_id: int | None = None
    created_at: datetime | None = None
