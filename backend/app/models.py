from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text as sa_text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


BIGINT = BigInteger().with_variant(Integer, "sqlite")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(24), default="personal")
    status: Mapped[str] = mapped_column(String(24), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_user_last_seen", "user_id", "last_seen_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    device_name: Mapped[str] = mapped_column(String(128), default="未知设备")
    user_agent: Mapped[str] = mapped_column(String(512), default="")
    ip_address_masked: Mapped[str] = mapped_column(String(64), default="未知网络")
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailOutbox(Base):
    __tablename__ = "email_outbox"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'sending', 'sent', 'failed')", name="ck_email_outbox_status"),
        CheckConstraint("attempts >= 0", name="ck_email_outbox_attempts"),
        Index("ix_email_outbox_status_next", "status", "next_attempt_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    destination: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    text_body: Mapped[str] = mapped_column(Text)
    action_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_auth_rate_limits_attempts"),
    )

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SupplierApplication(Base):
    __tablename__ = "supplier_applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_supplier_applications_status",
        ),
        CheckConstraint("version > 0", name="ck_supplier_applications_version"),
        Index("ix_supplier_applications_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    company_name: Mapped[str] = mapped_column(String(128))
    contact_name: Mapped[str] = mapped_column(String(64))
    contact_phone: Mapped[str] = mapped_column(String(32))
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    version: Mapped[int] = mapped_column(default=1)


class SupplierApplicationEvent(Base):
    __tablename__ = "supplier_application_events"
    __table_args__ = (
        Index(
            "ix_supplier_application_events_application_created",
            "application_id",
            "created_at",
        ),
        Index("ix_supplier_application_events_event_type", "event_type"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_applications.id", ondelete="CASCADE")
    )
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    actor_role: Mapped[str] = mapped_column(String(24))
    event_type: Mapped[str] = mapped_column(String(32))
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str] = mapped_column(String(24))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'pending_review', 'approved', 'published', 'rejected', 'archived')",
            name="ck_products_status",
        ),
        CheckConstraint("available_quantity = 1", name="ck_products_single_server"),
        CheckConstraint("unit_price_ch >= 0", name="ck_products_unit_price"),
        CheckConstraint("price_unit = 'server_hour'", name="ck_products_price_unit"),
        CheckConstraint("version > 0", name="ck_products_version"),
        Index("ix_products_resource_no", "resource_no", unique=True),
        Index("ix_products_status_updated", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    resource_no: Mapped[str] = mapped_column(String(32))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    gpu_model: Mapped[str] = mapped_column(String(64), index=True)
    memory: Mapped[str] = mapped_column(String(32))
    gpu_memory_gb: Mapped[int | None] = mapped_column(nullable=True)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cpu_cores: Mapped[int | None] = mapped_column(nullable=True)
    ram_gb: Mapped[int | None] = mapped_column(nullable=True)
    disk_gb: Mapped[int | None] = mapped_column(nullable=True)
    bandwidth_mbps: Mapped[int | None] = mapped_column(nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    unit_price: Mapped[Decimal] = mapped_column("unit_price_ch", Numeric(18, 6))
    price_currency: Mapped[str] = mapped_column(String(8), default="USD")
    price_unit: Mapped[str] = mapped_column(String(32), default="server_hour")
    total_quantity: Mapped[int] = mapped_column("available_quantity", default=1)
    source_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    version: Mapped[int] = mapped_column(default=1)


class ProductPriceVersion(Base):
    __tablename__ = "product_price_versions"
    __table_args__ = (
        UniqueConstraint("product_id", "version", name="uq_product_price_version"),
        CheckConstraint("amount >= 0", name="ck_product_price_versions_amount"),
        CheckConstraint("version > 0", name="ck_product_price_versions_version"),
        Index("ix_product_price_versions_product_created", "product_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column()
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(8))
    price_unit: Mapped[str] = mapped_column(String(32))
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketPriceSnapshot(Base):
    __tablename__ = "market_price_snapshots"
    __table_args__ = (
        UniqueConstraint("source", "gpu_model", "bucket_hour", name="uq_market_price_snapshot_hour"),
        CheckConstraint("min_price >= 0", name="ck_market_price_snapshots_min_price"),
        CheckConstraint("median_price >= 0", name="ck_market_price_snapshots_median_price"),
        CheckConstraint("available >= 0", name="ck_market_price_snapshots_available"),
        Index("ix_market_price_snapshots_model_observed", "gpu_model", "observed_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), default="getdeploying")
    gpu_model: Mapped[str] = mapped_column(String(64))
    bucket_hour: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    min_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    median_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    available: Mapped[int] = mapped_column(default=0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    price_unit: Mapped[str] = mapped_column(String(32), default="gpu_hour")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProductReviewEvent(Base):
    __tablename__ = "product_review_events"
    __table_args__ = (
        Index("ix_product_review_events_product_created", "product_id", "created_at"),
        Index("ix_product_review_events_event_type", "event_type"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    actor_role: Mapped[str] = mapped_column(String(24))
    event_type: Mapped[str] = mapped_column(String(32))
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str] = mapped_column(String(24))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"
    __table_args__ = (
        UniqueConstraint("reservation_no", name="uq_inventory_reservations_no"),
        UniqueConstraint("order_id", name="uq_inventory_reservations_order"),
        CheckConstraint(
            "status IN ('reserved', 'allocated', 'released')",
            name="ck_inventory_reservations_status",
        ),
        CheckConstraint("quantity > 0", name="ck_inventory_reservations_quantity"),
        CheckConstraint("version > 0", name="ck_inventory_reservations_version"),
        Index("ix_inventory_reservations_product_status", "product_id", "status"),
        Index("ix_inventory_reservations_supplier_status", "supplier_id", "status"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    reservation_no: Mapped[str] = mapped_column(String(32))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    order_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("orders.id"))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    quantity: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(24), default="reserved")
    release_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    allocated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    version: Mapped[int] = mapped_column(default=1)


class CommunityPost(Base):
    __tablename__ = "community_posts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(24), default="article")
    source_name: Mapped[str] = mapped_column(String(128))
    source_url: Mapped[str] = mapped_column(String(1024), unique=True)
    rights_status: Mapped[str] = mapped_column(String(32), default="link_summary_allowed")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NewsSource(Base):
    __tablename__ = "news_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    feed_url: Mapped[str] = mapped_column(String(1024), unique=True)
    site_url: Mapped[str] = mapped_column(String(1024))
    category: Mapped[str] = mapped_column(String(32), default="industry")
    is_official: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NewsArticle(Base):
    __tablename__ = "news_articles"
    __table_args__ = (UniqueConstraint("normalized_url", name="uq_news_articles_normalized_url"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("news_sources.id"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    title_original: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    content_format: Mapped[str] = mapped_column(String(16), default="html")
    ingestion_method: Mapped[str] = mapped_column(String(24), default="official_rss", index=True)
    original_url: Mapped[str] = mapped_column(String(2048))
    normalized_url: Mapped[str] = mapped_column(String(2048))
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    category: Mapped[str] = mapped_column(String(32), index=True, default="industry")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    language: Mapped[str] = mapped_column(String(16), default="unknown")
    content_fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), index=True, default="published")
    view_count: Mapped[int] = mapped_column(default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class ArticleComment(Base):
    __tablename__ = "article_comments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("news_articles.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    content_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24), default="checking", index=True)
    violation_category: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    moderation_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CommentReport(Base):
    __tablename__ = "comment_reports"
    __table_args__ = (UniqueConstraint("comment_id", "reporter_id", name="uq_comment_reporter"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    comment_id: Mapped[int] = mapped_column(ForeignKey("article_comments.id"), index=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    reason: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CommentRestriction(Base):
    __tablename__ = "comment_restrictions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    restricted_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BuyRequest(Base):
    __tablename__ = "buy_requests"
    __table_args__ = (
        CheckConstraint("request_type IN ('cloud_compute', 'offline_device')", name="ck_buy_requests_type"),
        CheckConstraint(
            "status IN ('draft', 'reviewing', 'published', 'negotiating', 'matched', 'completed', 'rejected', 'closed', 'expired')",
            name="ck_buy_requests_status",
        ),
        CheckConstraint("visibility IN ('public', 'invited', 'private')", name="ck_buy_requests_visibility"),
        CheckConstraint("delivery_mode IN ('remote', 'dedicated', 'negotiable')", name="ck_buy_requests_delivery_mode"),
        CheckConstraint("gpu_quantity > 0", name="ck_buy_requests_gpu_quantity"),
        CheckConstraint("min_gpu_memory_gb IS NULL OR min_gpu_memory_gb > 0", name="ck_buy_requests_gpu_memory"),
        CheckConstraint("budget_amount IS NULL OR budget_amount >= 0", name="ck_buy_requests_budget"),
        CheckConstraint(
            "expected_duration_hours IS NULL OR expected_duration_hours > 0",
            name="ck_buy_requests_duration",
        ),
        CheckConstraint("version > 0", name="ck_buy_requests_version"),
        Index("ix_buy_requests_request_no", "request_no", unique=True),
        Index("ix_buy_requests_buyer_id", "buyer_id"),
        Index("ix_buy_requests_public_feed", "status", "visibility", "published_at"),
        Index("ix_buy_requests_quote_deadline", "quote_deadline_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    request_no: Mapped[str] = mapped_column(String(32))
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    request_type: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(24), default="draft")
    visibility: Mapped[str] = mapped_column(String(16), default="public")
    gpu_model: Mapped[str] = mapped_column(String(64))
    min_gpu_memory_gb: Mapped[int | None] = mapped_column(nullable=True)
    gpu_quantity: Mapped[int] = mapped_column(default=1)
    region_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    delivery_mode: Mapped[str] = mapped_column(String(24), default="remote")
    budget_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    budget_currency: Mapped[str] = mapped_column(String(8), default="USD")
    budget_unit: Mapped[str] = mapped_column(String(32), default="gpu_hour")
    quote_deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=False)
    expected_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_duration_hours: Mapped[int | None] = mapped_column(nullable=True)
    requirements: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    version: Mapped[int] = mapped_column(default=1)


class CloudComputeRequestDetail(Base):
    __tablename__ = "cloud_compute_request_details"
    __table_args__ = (
        CheckConstraint("min_cpu_cores IS NULL OR min_cpu_cores > 0", name="ck_cloud_details_cpu"),
        CheckConstraint("min_ram_gb IS NULL OR min_ram_gb > 0", name="ck_cloud_details_ram"),
        CheckConstraint("min_disk_gb IS NULL OR min_disk_gb > 0", name="ck_cloud_details_disk"),
        CheckConstraint("min_download_mbps IS NULL OR min_download_mbps > 0", name="ck_cloud_details_download"),
    )

    buy_request_id: Mapped[int] = mapped_column(
        BIGINT,
        ForeignKey("buy_requests.id", ondelete="CASCADE"),
        primary_key=True,
    )
    min_cpu_cores: Mapped[int | None] = mapped_column(nullable=True)
    min_ram_gb: Mapped[int | None] = mapped_column(nullable=True)
    min_disk_gb: Mapped[int | None] = mapped_column(nullable=True)
    min_download_mbps: Mapped[int | None] = mapped_column(nullable=True)
    public_ip_required: Mapped[bool] = mapped_column(Boolean, default=False)
    container_image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    software_stack: Mapped[list[str]] = mapped_column(JSON, default=list)
    special_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)


class BuyRequestContact(Base):
    __tablename__ = "buy_request_contacts"
    __table_args__ = (
        CheckConstraint(
            "visible_after IN ('quote_submitted', 'shortlisted', 'accepted', 'manual_grant')",
            name="ck_buy_request_contacts_visibility",
        ),
    )

    buy_request_id: Mapped[int] = mapped_column(
        BIGINT,
        ForeignKey("buy_requests.id", ondelete="CASCADE"),
        primary_key=True,
    )
    contact_name: Mapped[str] = mapped_column(String(64))
    contact_phone_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_email_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_wechat_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    encryption_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    visible_after: Mapped[str] = mapped_column(String(24), default="accepted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BuyRequestQuote(Base):
    __tablename__ = "buy_request_quotes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'submitted', 'shortlisted', 'accepted', 'rejected', 'withdrawn', 'expired')",
            name="ck_buy_request_quotes_status",
        ),
        CheckConstraint("price_amount >= 0", name="ck_buy_request_quotes_price"),
        CheckConstraint("available_quantity > 0", name="ck_buy_request_quotes_quantity"),
        CheckConstraint(
            "delivery_time_hours IS NULL OR delivery_time_hours >= 0",
            name="ck_buy_request_quotes_delivery_time",
        ),
        CheckConstraint("version > 0", name="ck_buy_request_quotes_version"),
        Index("ix_buy_request_quotes_quote_no", "quote_no", unique=True),
        Index(
            "uq_buy_request_supplier_active_quote",
            "buy_request_id",
            "supplier_id",
            unique=True,
            postgresql_where=sa_text("status IN ('draft', 'submitted', 'shortlisted', 'accepted')"),
            sqlite_where=sa_text("status IN ('draft', 'submitted', 'shortlisted', 'accepted')"),
        ),
        Index("ix_buy_request_quotes_request_status", "buy_request_id", "status"),
        Index("ix_buy_request_quotes_supplier_status", "supplier_id", "status"),
        Index("ix_buy_request_quotes_valid_until", "valid_until"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    quote_no: Mapped[str] = mapped_column(String(32))
    buy_request_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("buy_requests.id"))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    price_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    price_currency: Mapped[str] = mapped_column(String(8))
    price_unit: Mapped[str] = mapped_column(String(32))
    available_quantity: Mapped[int] = mapped_column()
    delivery_time_hours: Mapped[int | None] = mapped_column(nullable=True)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    service_description: Mapped[str] = mapped_column(Text, default="")
    buyer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    version: Mapped[int] = mapped_column(default=1)


class BuyRequestEvent(Base):
    __tablename__ = "buy_request_events"
    __table_args__ = (
        Index("ix_buy_request_events_request_created", "buy_request_id", "created_at"),
        Index("ix_buy_request_events_event_type", "event_type"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    buy_request_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("buy_requests.id"))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_role: Mapped[str] = mapped_column(String(24))
    event_type: Mapped[str] = mapped_column(String(64))
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("buy_request_id", name="uq_orders_buy_request_id"),
        UniqueConstraint("accepted_quote_id", name="uq_orders_accepted_quote_id"),
        CheckConstraint(
            "status IN ('pending_confirmation', 'confirmed', 'delivering', "
            "'delivered', 'completed', 'cancelled')",
            name="ck_orders_status",
        ),
        CheckConstraint("amount >= 0", name="ck_orders_amount"),
        CheckConstraint("quantity > 0", name="ck_orders_quantity"),
        CheckConstraint("order_source IN ('quote', 'direct')", name="ck_orders_source"),
        CheckConstraint("environment IN ('live', 'sandbox')", name="ck_orders_environment"),
        CheckConstraint(
            "payment_status IN ('not_required', 'pending', 'paid', 'refund_pending', 'refunded')",
            name="ck_orders_payment_status",
        ),
        CheckConstraint(
            "duration_hours IS NULL OR duration_hours > 0",
            name="ck_orders_duration_hours",
        ),
        CheckConstraint("version > 0", name="ck_orders_version"),
        Index("ix_orders_order_no", "order_no", unique=True),
        Index("ix_orders_buyer_status", "buyer_id", "status"),
        Index("ix_orders_supplier_status", "supplier_id", "status"),
        Index("ix_orders_product_created", "product_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(32))
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    buy_request_id: Mapped[int | None] = mapped_column(BIGINT, ForeignKey("buy_requests.id"), nullable=True)
    accepted_quote_id: Mapped[int | None] = mapped_column(BIGINT, ForeignKey("buy_request_quotes.id"), nullable=True)
    product_id: Mapped[int | None] = mapped_column(BIGINT, ForeignKey("products.id"), nullable=True)
    order_source: Mapped[str] = mapped_column(String(16), default="quote")
    environment: Mapped[str] = mapped_column(String(16), default="live")
    payment_status: Mapped[str] = mapped_column(String(24), default="not_required")
    duration_hours: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending_confirmation")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(8))
    price_unit: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[int] = mapped_column()
    snapshot: Mapped[dict] = mapped_column(JSON)
    buyer_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supplier_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    version: Mapped[int] = mapped_column(default=1)


class OrderEvent(Base):
    __tablename__ = "order_events"
    __table_args__ = (
        Index("ix_order_events_order_created", "order_id", "created_at"),
        Index("ix_order_events_event_type", "event_type"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("orders.id"))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_role: Mapped[str] = mapped_column(String(24))
    event_type: Mapped[str] = mapped_column(String(64))
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SandboxInstance(Base):
    __tablename__ = "sandbox_instances"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_sandbox_instances_order"),
        CheckConstraint(
            "status IN ('pending', 'running', 'stopped')",
            name="ck_sandbox_instances_status",
        ),
        CheckConstraint("run_count >= 0", name="ck_sandbox_instances_run_count"),
        CheckConstraint("usage_seconds >= 0", name="ck_sandbox_instances_usage"),
        Index("ix_sandbox_instances_buyer_status", "buyer_id", "status"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    instance_no: Mapped[str] = mapped_column(String(32), unique=True)
    order_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("orders.id"))
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    runtime: Mapped[str] = mapped_column(String(32), default="local_cpu")
    run_count: Mapped[int] = mapped_column(default=0)
    usage_seconds: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BuyerSshKey(Base):
    __tablename__ = "buyer_ssh_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "fingerprint_sha256", name="uq_buyer_ssh_keys_user_fingerprint"),
        CheckConstraint("status IN ('active', 'revoked')", name="ck_buyer_ssh_keys_status"),
        CheckConstraint("version > 0", name="ck_buyer_ssh_keys_version"),
        Index("ix_buyer_ssh_keys_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(64))
    algorithm: Mapped[str] = mapped_column(String(48))
    fingerprint_sha256: Mapped[str] = mapped_column(String(128))
    public_key: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(default=1)


class MerchantServer(Base):
    __tablename__ = "merchant_servers"
    __table_args__ = (
        UniqueConstraint("product_id", name="uq_merchant_servers_product"),
        CheckConstraint(
            "status IN ('registered', 'online', 'offline', 'maintenance', 'retired')",
            name="ck_merchant_servers_status",
        ),
        CheckConstraint("ssh_port > 0 AND ssh_port <= 65535", name="ck_merchant_servers_ssh_port"),
        CheckConstraint("version > 0", name="ck_merchant_servers_version"),
        CheckConstraint(
            "hardware_verification_status IN ('pending', 'verified', 'mismatch', 'stale', 'unavailable')",
            name="ck_merchant_servers_hardware_verification_status",
        ),
        CheckConstraint(
            "agent_service_status IN ('pending', 'healthy', 'unhealthy', 'stale', 'unavailable')",
            name="ck_merchant_servers_agent_service_status",
        ),
        Index("ix_merchant_servers_supplier_status", "supplier_id", "status"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    server_no: Mapped[str] = mapped_column(String(32), unique=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    product_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("products.id", ondelete="CASCADE"))
    public_host: Mapped[str] = mapped_column(String(255))
    ssh_port: Mapped[int] = mapped_column(default=22)
    ssh_username: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="registered")
    agent_mode: Mapped[str] = mapped_column(String(24), default="local_simulator")
    agent_certificate_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent_device_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    agent_public_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    agent_platform: Mapped[str | None] = mapped_column(String(16), nullable=True)
    agent_arch: Mapped[str | None] = mapped_column(String(16), nullable=True)
    agent_hostname: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent_capabilities: Mapped[list] = mapped_column(JSON, default=list)
    hardware_inventory: Mapped[dict] = mapped_column(JSON, default=dict)
    hardware_inventory_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hardware_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hardware_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hardware_verification_status: Mapped[str] = mapped_column(String(16), default="pending")
    hardware_mismatches: Mapped[list] = mapped_column(JSON, default=list)
    agent_service_checks: Mapped[dict] = mapped_column(JSON, default=dict)
    agent_service_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    agent_service_status: Mapped[str] = mapped_column(String(16), default="pending")
    agent_enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    agent_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(default=1)


class AccessLease(Base):
    __tablename__ = "access_leases"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_access_leases_order"),
        CheckConstraint(
            "status IN ('pending_authorization', 'active', 'grace', 'expired', 'revoked', 'failed')",
            name="ck_access_leases_status",
        ),
        CheckConstraint("ssh_port > 0 AND ssh_port <= 65535", name="ck_access_leases_ssh_port"),
        CheckConstraint("version > 0", name="ck_access_leases_version"),
        Index("ix_access_leases_buyer_status", "buyer_id", "status"),
        Index("ix_access_leases_supplier_status", "supplier_id", "status"),
        Index("ix_access_leases_expiry_status", "expires_at", "status"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    lease_no: Mapped[str] = mapped_column(String(32), unique=True)
    order_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("orders.id"))
    server_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("merchant_servers.id"))
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    ssh_key_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("buyer_ssh_keys.id"))
    status: Mapped[str] = mapped_column(String(32), default="pending_authorization")
    connection_host: Mapped[str] = mapped_column(String(255))
    ssh_port: Mapped[int] = mapped_column(default=22)
    ssh_username: Mapped[str] = mapped_column(String(64))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grace_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    access_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cleanup_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(default=1)


class AgentCommand(Base):
    __tablename__ = "agent_commands"
    __table_args__ = (
        CheckConstraint(
            "action IN ('authorize_key', 'revoke_key', 'cleanup_account')",
            name="ck_agent_commands_action",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_agent_commands_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_agent_commands_attempts"),
        Index("ix_agent_commands_server_status", "server_id", "status"),
        Index("ix_agent_commands_lease_created", "lease_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    command_no: Mapped[str] = mapped_column(String(32), unique=True)
    server_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("merchant_servers.id"))
    lease_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("access_leases.id"))
    action: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(default=0)
    result_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentEnrollmentToken(Base):
    __tablename__ = "agent_enrollment_tokens"
    __table_args__ = (
        UniqueConstraint(
            "token_hash", name="agent_enrollment_tokens_token_hash_key"
        ),
        Index("ix_agent_enrollment_tokens_token_hash", "token_hash", unique=True),
        Index("ix_agent_enrollment_tokens_server_expires", "server_id", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    server_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("merchant_servers.id", ondelete="CASCADE"), index=True
    )
    supplier_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentRequestNonce(Base):
    __tablename__ = "agent_request_nonces"
    __table_args__ = (Index("ix_agent_request_nonces_expires", "expires_at"),)

    nonce: Mapped[str] = mapped_column(String(64), primary_key=True)
    server_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("merchant_servers.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaymentIntent(Base):
    __tablename__ = "payment_intents"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_intents_amount"),
        CheckConstraint(
            "status IN ('created', 'provider_pending', 'succeeded', 'failed', "
            "'cancelled', 'expired', 'refund_pending', 'refunded')",
            name="ck_payment_intents_status",
        ),
        CheckConstraint("version > 0", name="ck_payment_intents_version"),
        Index("ix_payment_intents_payment_no", "payment_no", unique=True),
        Index("ix_payment_intents_user_created", "user_id", "created_at"),
        Index("ix_payment_intents_status_updated", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    payment_no: Mapped[str] = mapped_column(String(32))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    order_id: Mapped[int | None] = mapped_column(BIGINT, ForeignKey("orders.id"), nullable=True)
    purpose: Mapped[str] = mapped_column(String(32), default="wallet_recharge")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    status: Mapped[str] = mapped_column(String(24), default="created")
    provider: Mapped[str] = mapped_column(String(32), default="disabled")
    provider_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    checkout_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_payload: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(default=1)


class RefundRequest(Base):
    __tablename__ = "refund_requests"
    __table_args__ = (
        UniqueConstraint("payment_intent_id", name="uq_refund_requests_payment_intent"),
        CheckConstraint("amount > 0", name="ck_refund_requests_amount"),
        CheckConstraint(
            "status IN ('requested', 'requires_manual', 'processing', 'completed', 'rejected')",
            name="ck_refund_requests_status",
        ),
        CheckConstraint("version > 0", name="ck_refund_requests_version"),
        Index("ix_refund_requests_status_created", "status", "created_at"),
        Index("ix_refund_requests_order", "order_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    refund_no: Mapped[str] = mapped_column(String(32), unique=True)
    payment_intent_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("payment_intents.id", ondelete="CASCADE")
    )
    order_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("orders.id"))
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(8))
    provider: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="requested")
    reason_code: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(500))
    provider_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    admin_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(default=1)


class PaymentWebhookEvent(Base):
    __tablename__ = "payment_webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_key", name="uq_payment_webhook_provider_event"),
        CheckConstraint(
            "status IN ('received', 'processed', 'rejected', 'failed')",
            name="ck_payment_webhook_events_status",
        ),
        Index("ix_payment_webhook_intent_created", "payment_intent_id", "created_at"),
        Index("ix_payment_webhook_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32))
    event_key: Mapped[str] = mapped_column(String(128))
    payment_intent_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("payment_intents.id", ondelete="CASCADE")
    )
    provider_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="received")
    payload_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id", "account_type", "currency", name="uq_ledger_account_owner_type_currency"
        ),
        CheckConstraint(
            "account_type IN ('user_available', 'user_frozen', 'platform_clearing', "
            "'platform_revenue', 'provider_clearing')",
            name="ck_ledger_accounts_type",
        ),
        CheckConstraint("normal_side IN ('debit', 'credit')", name="ck_ledger_accounts_normal_side"),
        CheckConstraint("status IN ('active', 'frozen', 'closed')", name="ck_ledger_accounts_status"),
        Index("ix_ledger_accounts_code", "account_code", unique=True),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    account_code: Mapped[str] = mapped_column(String(64))
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    account_type: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(8))
    normal_side: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LedgerJournal(Base):
    __tablename__ = "ledger_journals"
    __table_args__ = (
        CheckConstraint("status IN ('posted', 'reversed')", name="ck_ledger_journals_status"),
        Index("ix_ledger_journals_no", "journal_no", unique=True),
        Index("ix_ledger_journals_reference", "reference_type", "reference_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    journal_no: Mapped[str] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(48))
    reference_type: Mapped[str] = mapped_column(String(32))
    reference_id: Mapped[str] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(8))
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="posted")
    metadata_payload: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("direction IN ('debit', 'credit')", name="ck_ledger_entries_direction"),
        CheckConstraint("amount > 0", name="ck_ledger_entries_amount"),
        Index("ix_ledger_entries_journal", "journal_id"),
        Index("ix_ledger_entries_account_created", "account_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    journal_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("ledger_journals.id"))
    account_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("ledger_accounts.id"))
    direction: Mapped[str] = mapped_column(String(8))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SupplierWithdrawal(Base):
    __tablename__ = "supplier_withdrawals"
    __table_args__ = (
        UniqueConstraint("withdrawal_no", name="uq_supplier_withdrawals_no"),
        UniqueConstraint("idempotency_key", name="uq_supplier_withdrawals_idempotency"),
        CheckConstraint("amount > 0", name="ck_supplier_withdrawals_amount"),
        CheckConstraint("currency = 'CNY'", name="ck_supplier_withdrawals_currency"),
        CheckConstraint(
            "status IN ('requested', 'approved', 'rejected', 'paid', 'cancelled')",
            name="ck_supplier_withdrawals_status",
        ),
        CheckConstraint("version > 0", name="ck_supplier_withdrawals_version"),
        Index("ix_supplier_withdrawals_supplier_created", "supplier_id", "created_at"),
        Index("ix_supplier_withdrawals_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    withdrawal_no: Mapped[str] = mapped_column(String(32))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    status: Mapped[str] = mapped_column(String(24), default="requested")
    payout_method: Mapped[str] = mapped_column(String(32), default="manual_bank_transfer")
    payout_details_encrypted: Mapped[str] = mapped_column(Text)
    payout_account_last4: Mapped[str] = mapped_column(String(8))
    idempotency_key: Mapped[str] = mapped_column(String(64))
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(default=1)


class KycApplication(Base):
    __tablename__ = "kyc_applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'pending', 'approved', 'rejected', 'expired')",
            name="ck_kyc_applications_status",
        ),
        CheckConstraint("version > 0", name="ck_kyc_applications_version"),
        Index("ix_kyc_applications_user_id", "user_id", unique=True),
        Index("ix_kyc_applications_status_updated", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(24), default="draft")
    provider: Mapped[str] = mapped_column(String(32), default="disabled")
    provider_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verification_type: Mapped[str] = mapped_column(String(24), default="individual")
    country_code: Mapped[str] = mapped_column(String(2), default="CN")
    subject_details_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject_identifier_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    declaration_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(default=1)


class StoredObject(Base):
    __tablename__ = "stored_objects"
    __table_args__ = (
        CheckConstraint(
            "category IN ('kyc_document', 'supplier_document', 'contract', "
            "'delivery_artifact', 'general_private')",
            name="ck_stored_objects_category",
        ),
        CheckConstraint(
            "status IN ('initiating', 'uploading', 'available', 'quarantined', "
            "'failed', 'deleted')",
            name="ck_stored_objects_status",
        ),
        CheckConstraint("size_bytes > 0", name="ck_stored_objects_size"),
        Index("ix_stored_objects_object_no", "object_no", unique=True),
        Index("ix_stored_objects_owner_created", "owner_user_id", "created_at"),
        Index("ix_stored_objects_status_updated", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    object_no: Mapped[str] = mapped_column(String(32))
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kyc_application_id: Mapped[int | None] = mapped_column(
        BIGINT, ForeignKey("kyc_applications.id"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(32), default="disabled")
    bucket: Mapped[str | None] = mapped_column(String(128), nullable=True)
    object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(BIGINT)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="initiating")
    is_private: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UploadSession(Base):
    __tablename__ = "upload_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'uploading', 'completed', 'expired', 'failed')",
            name="ck_upload_sessions_status",
        ),
        Index("ix_upload_sessions_expires", "status", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stored_object_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("stored_objects.id"), unique=True
    )
    provider_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserAddress(Base):
    __tablename__ = "user_addresses"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_user_addresses_version"),
        Index("ix_user_addresses_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(32), default="常用地址")
    recipient_name: Mapped[str] = mapped_column(String(64))
    phone: Mapped[str] = mapped_column(String(32))
    country_code: Mapped[str] = mapped_column(String(2), default="CN")
    province: Mapped[str] = mapped_column(String(64))
    city: Mapped[str] = mapped_column(String(64))
    district: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address_line: Mapped[str] = mapped_column(String(255))
    postal_code: Mapped[str | None] = mapped_column(String(24), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    version: Mapped[int] = mapped_column(default=1)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "category IN ('order', 'asset', 'review', 'security', 'team', 'dispute', 'payment', 'system')",
            name="ck_notifications_category",
        ),
        Index("ix_notifications_user_read_created", "user_id", "is_read", "created_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(24), default="system")
    title: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text)
    action_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SupplierProfile(Base):
    __tablename__ = "supplier_profiles"
    __table_args__ = (CheckConstraint("version > 0", name="ck_supplier_profiles_version"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    store_name: Mapped[str] = mapped_column(String(128))
    contact_name: Mapped[str] = mapped_column(String(64))
    contact_phone: Mapped[str] = mapped_column(String(32))
    service_regions: Mapped[list] = mapped_column(JSON, default=list)
    introduction: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    version: Mapped[int] = mapped_column(default=1)


class DisputeCase(Base):
    __tablename__ = "dispute_cases"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'under_review', 'resolved', 'rejected', 'cancelled')",
            name="ck_dispute_cases_status",
        ),
        CheckConstraint(
            "reason IN ('not_delivered', 'service_unavailable', 'configuration_mismatch', 'billing_issue', 'other')",
            name="ck_dispute_cases_reason",
        ),
        CheckConstraint(
            "resolution_action IS NULL OR resolution_action IN ('release_to_supplier', 'refund_buyer')",
            name="ck_dispute_cases_resolution_action",
        ),
        CheckConstraint("version > 0", name="ck_dispute_cases_version"),
        Index("ix_dispute_cases_no", "dispute_no", unique=True),
        Index("ix_dispute_cases_opened_status", "opened_by_user_id", "status"),
        Index("ix_dispute_cases_order_created", "order_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    dispute_no: Mapped[str] = mapped_column(String(32))
    order_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("orders.id"))
    opened_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    counterparty_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(24), default="open")
    reason: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    attachment_object_ids: Mapped[list] = mapped_column(JSON, default=list)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resolved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    version: Mapped[int] = mapped_column(default=1)


class DisputeEvent(Base):
    __tablename__ = "dispute_events"
    __table_args__ = (Index("ix_dispute_events_case_created", "dispute_id", "created_at"),)

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    dispute_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("dispute_cases.id", ondelete="CASCADE"))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(48))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_teams_version"),
        Index("ix_teams_owner_created", "owner_user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    version: Mapped[int] = mapped_column(default=1)


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_members_team_user"),
        CheckConstraint("role IN ('owner', 'admin', 'member', 'viewer')", name="ck_team_members_role"),
        CheckConstraint("status IN ('active', 'removed')", name="ck_team_members_status"),
        Index("ix_team_members_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("teams.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16), default="member")
    status: Mapped[str] = mapped_column(String(16), default="active")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeamInvitation(Base):
    __tablename__ = "team_invitations"
    __table_args__ = (
        UniqueConstraint("team_id", "email", name="uq_team_invitations_team_email"),
        CheckConstraint(
            "role IN ('admin', 'member', 'viewer')", name="ck_team_invitations_role"
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_team_invitations_status",
        ),
        Index("ix_team_invitations_email_status", "email", "status"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("teams.id", ondelete="CASCADE"))
    invited_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="member")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApiCredential(Base):
    __tablename__ = "api_credentials"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'revoked')", name="ck_api_credentials_status"),
        Index("ix_api_credentials_user_created", "user_id", "created_at"),
        Index("ix_api_credentials_secret_hash", "secret_hash", unique=True),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    key_prefix: Mapped[str] = mapped_column(String(20))
    secret_hash: Mapped[str] = mapped_column(String(64))
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
