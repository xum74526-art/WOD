from datetime import datetime

from sqlalchemy import Boolean, String, DateTime, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64))
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    # False means WOD has not verified ownership by SMS. Kai-only accounts use
    # an internal value; closed-test phone sign-ups keep the entered number only
    # as a login identifier. API serializers hide it while this flag is false.
    phone_bound: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    password: Mapped[str] = mapped_column(String(255))
    avatar: Mapped[str | None] = mapped_column(String(512), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="personal")  # personal / supplier
    supplier_status: Mapped[str] = mapped_column(String(16), default="none")  # none / pending / approved / rejected
    invited_by: Mapped[int | None] = mapped_column(nullable=True)  # 邀请人 user_id
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
