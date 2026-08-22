from typing import Any

from pydantic import BaseModel, ConfigDict


class OrmModel(BaseModel):
    """带 ORM 读取能力的输出模型基类。"""
    model_config = ConfigDict(from_attributes=True)


class ResponseBase(BaseModel):
    code: int = 0
    msg: str = "ok"
    data: Any = None


class PageQuery(BaseModel):
    page: int = 1
    page_size: int = 20
