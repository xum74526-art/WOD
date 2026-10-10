from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SupportMessageIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    conversation_id: int | None = Field(default=None, gt=0)
    client_message_id: str | None = Field(default=None, min_length=8, max_length=80)
    lang: Literal["zh", "en"] = "zh"

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("消息不能为空")
        return cleaned

    @field_validator("client_message_id")
    @classmethod
    def clean_client_message_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_:." for char in cleaned):
            raise ValueError("客户端消息标识无效")
        return cleaned


class SupportTicketIn(BaseModel):
    conversation_id: int = Field(gt=0)
    source_message_id: int | None = Field(default=None, gt=0)
    subject: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    category: str = Field(default="other", min_length=1, max_length=32)
    lang: Literal["zh", "en"] = "zh"

    @field_validator("subject", "description", "category")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("内容不能为空")
        return cleaned


class SupportMessageOut(BaseModel):
    id: int
    role: str
    content: str
    response_mode: str
    topic: str | None
    can_create_ticket: bool
    reply_to_id: int | None
    created_at: datetime


class SupportTicketOut(BaseModel):
    id: int
    ticket_no: str
    conversation_id: int
    subject: str
    description: str
    category: str
    status: str
    assigned_to: str | None
    created_at: datetime
    updated_at: datetime


class AdminSupportTicketActionIn(BaseModel):
    action: Literal["claim", "assign", "reply", "resolve", "close", "reopen"]
    expected_status: Literal["pending_unassigned", "assigned", "resolved", "closed"]
    assignee_user_id: int | None = Field(default=None, gt=0)
    reply: str | None = Field(default=None, max_length=2000)
    note: str | None = Field(default=None, max_length=500)
    request_id: str = Field(min_length=8, max_length=64)

    @field_validator("reply", "note")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("request_id")
    @classmethod
    def clean_request_id(cls, value: str) -> str:
        cleaned = value.strip()
        if any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_:" for char in cleaned):
            raise ValueError("请求标识无效")
        return cleaned
