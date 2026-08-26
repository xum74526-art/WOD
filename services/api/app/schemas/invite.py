from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


InviteQualificationStatus = Literal[
    "pending_identity",
    "pending_order",
    "qualified",
    "daily_cap_exceeded",
    "risk_rejected",
    "risk_review",
    "legacy_v1",
]
RewardAccrualStatus = Literal["not_applicable", "pending", "settled", "forfeited"]
InviteQualificationReason = Literal[
    "verified_identity_required",
    "first_cash_backed_order_required",
    "verified_identity_and_first_cash_order",
    "daily_qualified_limit_reached",
    "self_invite",
    "same_verified_identity",
    "identity_comparison_unavailable",
]


class InviteTierOut(BaseModel):
    min_qualified_count: int
    max_qualified_count: int | None
    rate_bps: int


class InviteSummaryOut(BaseModel):
    code: str
    invited_count: int
    qualified_count: int
    pending_identity_count: int = 0
    pending_order_count: int = 0
    daily_cap_exceeded_count: int = 0
    risk_rejected_count: int = 0
    risk_review_count: int = 0
    unverified_count: int = 0
    pending_count: int = 0
    rewarded_count: int = 0
    current_tier: str
    current_rate_bps: int = 0
    next_tier_hint: str
    tiers: list[InviteTierOut] = Field(default_factory=list)
    fixed_reward_card_hours: float = 58.0
    fixed_reward_total: float = 0
    fixed_reward_pending: float = 0
    commission_total: float = 0
    commission_pending: float = 0
    total_reward: float = 0
    pending_reward: float = 0
    daily_limit: int = 5
    daily_used: int = 0
    daily_remaining: int = 5
    # Deprecated compatibility aliases.
    daily_slots_used: int = 0
    daily_slots_remaining: int = 5
    next_reset_at: datetime
    rewards_enabled: bool
    rewards_withdrawable: Literal[False] = False
    rewards_transferable: Literal[False] = False
    eligible_friend_spend_card_hours: float = 0
    # Deprecated compatibility alias; new clients use the field above.
    total_eligible_consumption_card_hours: float = 0
    reward_mode: Literal["live", "disabled"]
    program_code: str
    policy_version: str
    business_timezone: str = "Asia/Shanghai"
    qualification_requirement: Literal["verified_identity_and_first_cash_order"] = (
        "verified_identity_and_first_cash_order"
    )


class InviteSummaryResponse(BaseModel):
    code: Literal[0] = 0
    msg: str = "ok"
    data: InviteSummaryOut


class InviteRelationshipOut(BaseModel):
    id: int
    invitee_phone_masked: str
    # Compatibility alias for installed V1 clients. New clients use the
    # explicitly named masked field above.
    invitee_phone: str
    # Installed V1 clients still read ``status``.
    status: str
    legacy_status: str
    reward_amount: float = 0
    rewarded_at: datetime | None = None
    qualification_status: InviteQualificationStatus
    qualification_reason: InviteQualificationReason | None = None
    identity_verified_at: datetime | None = None
    qualified_at: datetime | None = None
    qualification_day: date | None = None
    daily_slot: int | None = None
    qualification_order_id: int | None = None
    fixed_reward_amount: float = 0
    fixed_reward_status: RewardAccrualStatus = "not_applicable"
    created_at: datetime | None = None


class InviteRelationshipListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[InviteRelationshipOut]


class InviteRelationshipListResponse(BaseModel):
    code: Literal[0] = 0
    msg: str = "ok"
    data: InviteRelationshipListOut


class InviteCommissionOut(BaseModel):
    id: int
    source_type: Literal["order", "renewal"]
    order_id: int | None = None
    order_renewal_id: int | None = None
    base_card_hours: float
    rate_bps: int
    reward_card_hours: float
    status: Literal["pending", "settled", "forfeited"]
    policy_version: str
    created_at: datetime | None = None
    settled_at: datetime | None = None


class InviteCommissionListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[InviteCommissionOut]


class InviteCommissionListResponse(BaseModel):
    code: Literal[0] = 0
    msg: str = "ok"
    data: InviteCommissionListOut
