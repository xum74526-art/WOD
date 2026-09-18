from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    images: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of urls
    video: Mapped[str | None] = mapped_column(String(512), nullable=True)  # persisted platform video URL
    video_duration: Mapped[int | None] = mapped_column(Integer, nullable=True)  # seconds
    topic: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic_en: Mapped[str | None] = mapped_column(String(64), nullable=True)
    origin: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    content_type: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    source_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_item_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    source_author: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    rights_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    rights_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    video_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    embed_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    publish_batch: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    created_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy", index=True
    )
    last_modified_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy"
    )
    moderation_status: Mapped[str] = mapped_column(
        String(24), default="visible", server_default="visible", index=True
    )
    moderation_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    moderated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    client_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy", index=True
    )
    moderation_status: Mapped[str] = mapped_column(
        String(24), default="visible", server_default="visible", index=True
    )
    moderation_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    moderated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    __table_args__ = (
        Index(
            "uq_comments_user_client_request",
            "user_id",
            "client_request_id",
            unique=True,
            sqlite_where=client_request_id.is_not(None),
            postgresql_where=client_request_id.is_not(None),
        ),
    )


class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (
        Index("uq_likes_post_user", "post_id", "user_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Follow(Base):
    __tablename__ = "follows"
    __table_args__ = (
        Index("uq_follows_follower_following", "follower_id", "following_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    follower_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)  # 关注者
    following_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)  # 被关注者
    created_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CommunityBlock(Base):
    """A viewer-controlled block relation used to remove abusive users' content."""

    __tablename__ = "community_blocks"
    __table_args__ = (
        UniqueConstraint("blocker_user_id", "blocked_user_id", name="uq_community_blocks_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    blocker_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    blocked_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CommunityReport(Base):
    """Auditable user report for a community post, comment, or account."""

    __tablename__ = "community_reports"
    __table_args__ = (
        UniqueConstraint(
            "reporter_user_id", "target_type", "target_id",
            name="uq_community_reports_reporter_target",
        ),
        Index("ix_community_reports_queue", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    reporter_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(16), index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    reason: Mapped[str] = mapped_column(String(32))
    details: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(24), default="pending", server_default="pending", index=True
    )
    resolution: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_platform: Mapped[str] = mapped_column(
        String(16), default="legacy", server_default="legacy", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ContentSource(Base):
    __tablename__ = "content_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32))
    endpoint: Mapped[str] = mapped_column(Text)
    terms_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    rights_status: Mapped[str] = mapped_column(String(16), default="allowed")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_limit: Mapped[int] = mapped_column(Integer, default=5)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ContentIngestRun(Base):
    __tablename__ = "content_ingest_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch: Mapped[str] = mapped_column(String(32), index=True)
    target_count: Mapped[int] = mapped_column(Integer, default=10)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    published_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="running")
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
