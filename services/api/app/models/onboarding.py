from datetime import datetime

from sqlalchemy import String, DateTime, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ComputeOnboarding(Base):
    __tablename__ = "compute_onboardings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(16), default="personal")  # personal/company
    contact: Mapped[str] = mapped_column(String(64))
    phone: Mapped[str] = mapped_column(String(20))
    device_model: Mapped[str] = mapped_column(String(128))
    device_count: Mapped[int] = mapped_column(Integer, default=1)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="submitted")  # submitted/contacted/approved/rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
