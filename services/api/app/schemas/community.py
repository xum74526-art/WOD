from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import OrmModel


class PostCreateIn(BaseModel):
    content: str
    images: list[str] | None = None
    video: str | None = None
    video_duration: int | None = Field(default=None, ge=0, le=86400)
    topic: str | None = None


class PostOut(OrmModel):
    id: int
    user_id: int
    content: str
    images: list[str] | None = None
    video: str | None = None
    video_duration: int | None = None
    topic: str | None = None
    content_en: str | None = None
    topic_en: str | None = None
    origin: str | None = None
    content_type: str | None = None
    source_key: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    source_item_id: str | None = None
    source_author: str | None = None
    source_published_at: datetime | None = None
    summary: str | None = None
    rights_status: str | None = None
    video_provider: str | None = None
    video_id: str | None = None
    video_url: str | None = None
    embed_url: str | None = None
    thumbnail_url: str | None = None
    canonical_url: str | None = None
    publish_batch: str | None = None
    likes: int = 0
    comments: int = 0
    shares: int = 0
    created_at: datetime | None = None
    # 关联
    author_name: str | None = None
    author_avatar: str | None = None
    is_liked: bool = False


class CommentIn(BaseModel):
    content: str


class CommentOut(OrmModel):
    id: int
    post_id: int
    user_id: int
    content: str
    created_at: datetime | None = None
    author_name: str | None = None
