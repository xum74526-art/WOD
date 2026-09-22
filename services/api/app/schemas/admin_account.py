import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AdminUserActionIn(BaseModel):
    action: Literal["send_password_reset", "freeze", "unfreeze", "delete"]
    client_request_id: str = Field(
        min_length=12,
        max_length=64,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    reason: str = Field(min_length=4, max_length=500)
    confirm_username: str | None = Field(default=None, max_length=64)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 4:
            raise ValueError("请填写至少 4 个字的操作原因")
        if re.search(r"(?<!\d)\d{12,19}(?!\d)", normalized):
            raise ValueError("操作原因不得填写身份证号、银行卡号或其他长串敏感号码")
        return normalized
