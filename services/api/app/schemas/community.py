from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field, StrictBool

from app.schemas.common import OrmModel


class PostCreateIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    images: list[str] | None = None
    video: str | None = None
    video_duration: int | None = Field(default=None, ge=0, le=86400)
    topic: str | None = Field(default=None, max_length=64)


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
    is_following: bool = False
    is_own: bool = False


class CommentIn(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    client_request_id: str | None = Field(
        default=None,
        min_length=12,
        max_length=64,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )


class LikeStateIn(BaseModel):
    liked: StrictBool


class FollowStateIn(BaseModel):
    following: StrictBool


class CommentOut(OrmModel):
    id: int
    post_id: int
    user_id: int
    content: str
    created_at: datetime | None = None
    author_name: str | None = None
    post_comments: int | None = None
    is_own: bool = False


class PostListData(BaseModel):
    items: list[PostOut]
    total: int
    page: int
    page_size: int


class PostResponse(BaseModel):
    code: int = 0
    msg: str = "ok"
    data: PostOut


class PostListResponse(BaseModel):
    code: int = 0
    msg: str = "ok"
    data: PostListData


class CommentResponse(BaseModel):
    code: int = 0
    msg: str = "ok"
    data: CommentOut


class CommentListResponse(BaseModel):
    code: int = 0
    msg: str = "ok"
    data: list[CommentOut]


class CommunityReportIn(BaseModel):
    target_type: Literal["post", "comment", "user"]
    target_id: int = Field(gt=0)
    reason: Literal[
        "illegal", "harassment", "hate", "sexual", "violence", "scam",
        "privacy", "copyright", "spam", "other",
    ]
    details: str | None = Field(default=None, max_length=500)


class CommunityBlockStateIn(BaseModel):
    blocked: StrictBool


class CommunityReportReviewIn(BaseModel):
    resolution: Literal["dismissed", "content_removed", "user_restricted"]
    note: str | None = Field(default=None, max_length=500)
