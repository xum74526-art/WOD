from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, false, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "ux_users_recovery_email_fingerprint",
            "recovery_email_fingerprint",
            unique=True,
            sqlite_where=text("recovery_email_fingerprint IS NOT NULL"),
            postgresql_where=text("recovery_email_fingerprint IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64))
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    # False means WOD has not verified ownership by SMS. Kai-only accounts use
    # an internal value; unverified phone sign-ups keep the entered number only
    # as a login identifier. API serializers hide it while this flag is false.
    phone_bound: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    password: Mapped[str] = mapped_column(String(255))
    avatar: Mapped[str | None] = mapped_column(String(512), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="personal")  # personal / supplier
    supplier_status: Mapped[str] = mapped_column(String(16), default="none")  # none / pending / approved / rejected
    invited_by: Mapped[int | None] = mapped_column(nullable=True)  # 邀请人 user_id
    # Immutable audit origin captured from the authenticated/registered client.
    # This is an observability field only; authorization must continue to use
    # role/allow-list checks because public native client identifiers can be
    # copied by an attacker.
    created_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # Account deletion is independent of the business role and commerce flags.
    account_status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # The WOD-owned recovery address is encrypted at rest.  The keyed
    # fingerprint is the lookup/uniqueness key; KAI profile email claims are
    # deliberately kept separate in ``external_identities``.
    recovery_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    recovery_email_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recovery_email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Included in every newly issued JWT. Password recovery increments this
    # value so even legacy tokens without a server-side session are revoked.
    auth_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
