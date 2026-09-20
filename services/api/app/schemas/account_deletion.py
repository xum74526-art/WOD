from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, StrictBool


class DeletionBlocker(BaseModel):
    code: str
    message: str
    count: int


class DeletionEligibility(BaseModel):
    eligible: bool
    blockers: list[DeletionBlocker]
    automatic_actions: list[str]
    verification_methods: list[Literal["password", "kai"]]


class DeletionPasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class DeletionKaiStartIn(BaseModel):
    return_url: str | None = Field(default=None, max_length=1024)


class DeletionKaiProofIn(BaseModel):
    token: str = Field(min_length=40, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class DeletionAuthorizationOut(BaseModel):
    authorization_url: str


class DeletionTicketOut(BaseModel):
    ticket: str
    expires_at: datetime


class DeletionTicketIn(BaseModel):
    ticket: str = Field(min_length=40, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class DeletionSubmitIn(DeletionTicketIn):
    confirm: StrictBool


class DeletionStatus(BaseModel):
    status: Literal["verified", "blocked", "processing", "completed"]
    blockers: list[DeletionBlocker] = Field(default_factory=list)
    completed_at: datetime | None = None


class EligibilityResponse(BaseModel):
    code: int = 0
    msg: str = "ok"
    data: DeletionEligibility


class TicketResponse(BaseModel):
    code: int = 0
    msg: str = "ok"
    data: DeletionTicketOut


class AuthorizationResponse(BaseModel):
    code: int = 0
    msg: str = "ok"
    data: DeletionAuthorizationOut


class DeletionResponse(BaseModel):
    code: int = 0
    msg: str = "ok"
    data: DeletionStatus
