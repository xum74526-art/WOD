from typing import Literal

from pydantic import BaseModel, Field


class KaiStartIn(BaseModel):
    intent: Literal["login", "register"] = "login"
    return_url: str | None = Field(default=None, max_length=1024)
    client_id: str | None = Field(default=None, min_length=1, max_length=64)


class KaiBindStartIn(BaseModel):
    return_url: str | None = Field(default=None, max_length=1024)


class KaiTicketIn(BaseModel):
    ticket: str = Field(..., min_length=20, max_length=256)
