import asyncio
import io
import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy import and_, case, delete, func, insert, or_, text, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_platform, get_current_user, get_optional_current_user
from app.db.session import get_db
from app.models.community import (
    CommunityBlock,
    CommunityReport,
    Comment,
    ContentIngestRun,
    ContentSource,
    Follow,
    Like,
    Post,
)
from app.models.user import User
from app.schemas.community import (
    CommentIn,
    CommentListResponse,
    CommentOut,
    CommentResponse,
    CommunityBlockStateIn,
    CommunityReportIn,
    FollowStateIn,
    LikeStateIn,
    PostCreateIn,
    PostListResponse,
    PostOut,
    PostResponse,
)
from app.utils.response import BizError, success
from app.services.auth_session import normalize_platform
from app.services.community_safety import (
    safe_public_display_name,
    validate_public_community_text,
)
from app.services.community_video import (
    standardize_community_video,
    standardized_video_duration,
)

router = APIRouter(prefix="/api/community", tags=["community"])
public_router = APIRouter(prefix="/api/uploads/community", tags=["community-media"])

# The shared upload root is private. Only this exact community child directory
# can be served, through the validated route below. In particular, sibling
# directories such as uploads/id_cards are never mounted as static files.
UPLOAD_ROOT = (
    Path(settings.UPLOAD_ROOT).expanduser().resolve()
    if settings.UPLOAD_ROOT
    else Path(__file__).resolve().parents[2] / "uploads"
)
COMMUNITY_DIR = UPLOAD_ROOT / "community"
COMMUNITY_DIR.mkdir(parents=True, exist_ok=True)
COMMUNITY_FILENAME_RE = re.compile(r"^([0-9a-f]{32})\.(jpg|png|webp|mp4|mov|webm)$")
COMMUNITY_MEDIA_URL_RE = re.compile(
    r"^/uploads/community/([1-9]\d*)/([0-9a-f]{32})\.(jpg|png|webp|mp4|mov|webm)$"
)
IMAGE_EXTENSIONS = {"jpg", "png", "webp"}
VIDEO_EXTENSIONS = {"mp4", "mov", "webm"}
MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "webm": "video/webm",
}
VISIBLE_MODERATION_STATUS = "visible"
AUTO_HIDE_REPORT_THRESHOLD = 3


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _blocked_user_ids(db: Session, user_id: int | None) -> set[int]:
    if not user_id:
        return set()
    rows = db.query(
        CommunityBlock.blocker_user_id,
        CommunityBlock.blocked_user_id,
    ).filter(or_(
        CommunityBlock.blocker_user_id == user_id,
        CommunityBlock.blocked_user_id == user_id,
    )).all()
    return {
        int(blocked_id if int(blocker_id) == user_id else blocker_id)
        for blocker_id, blocked_id in rows
    }


def _reported_target_ids(db: Session, user_id: int | None, target_type: str) -> set[int]:
    if not user_id:
        return set()
    return {
        row[0]
        for row in db.query(CommunityReport.target_id).filter(
            CommunityReport.reporter_user_id == user_id,
            CommunityReport.target_type == target_type,
        ).all()
    }


def _file_size_limit_label(byte_count: int) -> str:
    for unit, divisor in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if byte_count >= divisor:
            value = byte_count / divisor
            return f"{value:g}{unit}"
    return f"{byte_count}B"


def _requested_extension(filename: str | None) -> str:
    extension = Path(filename or "").suffix.lower().lstrip(".")
    if extension == "jpeg":
        extension = "jpg"
    if extension not in MEDIA_TYPES:
        raise BizError("仅支持 JPG、PNG、WebP、MP4、MOV 或 WebM")
    return extension


def _verified_media_extension(content: bytes, expected_kind: str) -> str:
    """Identify media from bytes and verify decodable image payloads."""
    if content.startswith(b"\xff\xd8\xff"):
        detected, image_format = "jpg", "JPEG"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        detected, image_format = "png", "PNG"
    elif content.startswith(b"RIFF") and len(content) >= 12 and content[8:12] == b"WEBP":
        detected, image_format = "webp", "WEBP"
    else:
        detected = ""
        image_format = ""

    if detected:
        try:
            with Image.open(io.BytesIO(content)) as image:
                actual_format = (image.format or "").upper()
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise BizError("图片文件已损坏或格式无效")
        if actual_format != image_format:
            raise BizError("文件扩展名与实际格式不一致")
        return detected

    # MP4 and QuickTime MOV both use ISO-BMFF. QuickTime declares the `qt  `
    # major brand, so keep the original container extension instead of trusting
    # the client-provided filename.
    if len(content) >= 12 and content[4:8] == b"ftyp":
        return "mov" if content[8:12] == b"qt  " else "mp4"
    # WebM is EBML and declares the webm DocType near the beginning.
    if content.startswith(b"\x1a\x45\xdf\xa3") and b"webm" in content[:4096].lower():
        return "webm"
    if expected_kind == "image":
        raise BizError("图片文件已损坏或格式无效")
    raise BizError("视频文件签名无效")


def _media_path_from_url(url: str, user_id: int, expected_kind: str) -> Path:
    match = COMMUNITY_MEDIA_URL_RE.fullmatch(url.strip())
    if not match or int(match.group(1)) != user_id:
        raise BizError("社区媒体不存在或无权引用")
    extension = match.group(3)
    allowed = IMAGE_EXTENSIONS if expected_kind == "image" else VIDEO_EXTENSIONS
    if extension not in allowed:
        raise BizError("社区媒体类型不匹配")
    path = (COMMUNITY_DIR / match.group(1) / f"{match.group(2)}.{extension}").resolve()
    try:
        path.relative_to(COMMUNITY_DIR.resolve())
    except ValueError:
        raise BizError("社区媒体不存在或无权引用")
    if not path.is_file():
        raise BizError("社区媒体不存在或无权引用")
    return path


@router.post("/media/upload")
async def upload_community_media(
    media: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not settings.COMMUNITY_USER_MEDIA_ENABLED:
        raise BizError("当前版本仅支持发布文字动态", status_code=403)
    user_id = int(user.id)
    # Authentication and this route share the same cached Session. End its
    # read-only transaction before file IO and potentially long video
    # transcoding; the final account fence below safely reuses the Session.
    db.rollback()
    requested_extension = _requested_extension(media.filename)
    is_image = requested_extension in IMAGE_EXTENSIONS
    max_bytes = settings.COMMUNITY_IMAGE_MAX_BYTES if is_image else settings.COMMUNITY_VIDEO_MAX_BYTES
    content = await media.read(max_bytes + 1)
    if not content:
        raise BizError("请选择要上传的社区媒体")
    if len(content) > max_bytes:
        media_name = "图片" if is_image else "视频"
        raise BizError(f"社区{media_name}不能超过 {_file_size_limit_label(max_bytes)}")

    detected_extension = _verified_media_extension(content, "image" if is_image else "video")
    if detected_extension != requested_extension:
        raise BizError("文件扩展名与实际格式不一致")

    standardized_duration: int | None = None
    if not is_image:
        # Container signatures only identify the input. Decode and normalize it
        # before it becomes public so Android, iOS and web all receive the same
        # H.264/AAC MP4 profile and a server-measured duration.
        standardized = await asyncio.to_thread(
            standardize_community_video,
            content,
            detected_extension,
            max_bytes,
        )
        content = standardized.content
        detected_extension = "mp4"
        standardized_duration = standardized.duration_seconds

    from app.services.account_lifecycle import lock_active_user
    lock_active_user(db, user_id)

    user_dir = COMMUNITY_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{detected_extension}"
    destination = user_dir / filename
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".community_", suffix=".tmp", dir=user_dir, delete=False,
        ) as temp_file:
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_name = temp_file.name
        os.replace(temp_name, destination)
        temp_name = None
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)

    return success({
        "url": f"/uploads/community/{user_id}/{filename}",
        "kind": "image" if is_image else "video",
        "content_type": MEDIA_TYPES[detected_extension],
        "size": len(content),
        "duration": standardized_duration,
        "standardized": not is_image,
    })


def _public_community_media_path(user_id: int, filename: str) -> tuple[Path, str]:
    match = COMMUNITY_FILENAME_RE.fullmatch(filename)
    if user_id < 1 or not match:
        raise HTTPException(status_code=404, detail="社区媒体不存在")
    path = (COMMUNITY_DIR / str(user_id) / filename).resolve()
    try:
        path.relative_to(COMMUNITY_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="社区媒体不存在")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="社区媒体不存在")
    return path, match.group(2)


def _file_range(path: Path, start: int, end: int, chunk_size: int = 1024 * 1024):
    with path.open("rb") as source:
        source.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = source.read(min(chunk_size, remaining))
            if not chunk:
                return
            remaining -= len(chunk)
            yield chunk


@public_router.get("/{user_id}/{filename}", include_in_schema=False)
def public_community_media(
    user_id: int,
    filename: str,
    request: Request,
    db: Session = Depends(get_db, scope="function"),
):
    if not settings.COMMUNITY_USER_MEDIA_ENABLED:
        raise HTTPException(status_code=404, detail="社区媒体不存在")
    from app.services.account_lifecycle import active_user_exists
    if not active_user_exists(db, user_id):
        raise HTTPException(status_code=404, detail="社区媒体不存在")
    path, extension = _public_community_media_path(user_id, filename)
    common_headers = {
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
    }
    if extension in VIDEO_EXTENSIONS:
        common_headers["Accept-Ranges"] = "bytes"
        size = path.stat().st_size
        range_header = request.headers.get("range", "").strip()
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
            if not match or (not match.group(1) and not match.group(2)):
                raise HTTPException(
                    status_code=416, detail="视频范围无效",
                    headers={"Content-Range": f"bytes */{size}"},
                )
            if match.group(1):
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else size - 1
            else:
                suffix_length = int(match.group(2))
                if suffix_length <= 0:
                    raise HTTPException(
                        status_code=416, detail="视频范围无效",
                        headers={"Content-Range": f"bytes */{size}"},
                    )
                start = max(0, size - suffix_length)
                end = size - 1
            if start >= size or start > end:
                raise HTTPException(
                    status_code=416, detail="视频范围无效",
                    headers={"Content-Range": f"bytes */{size}"},
                )
            end = min(end, size - 1)
            headers = {
                **common_headers,
                "Content-Range": f"bytes {start}-{end}/{size}",
                "Content-Length": str(end - start + 1),
            }
            return StreamingResponse(
                _file_range(path, start, end),
                status_code=206,
                media_type=MEDIA_TYPES[extension],
                headers=headers,
            )
    return FileResponse(
        path,
        media_type=MEDIA_TYPES[extension],
        headers=common_headers,
    )


@dataclass(frozen=True)
class _PostOutputContext:
    authors: dict[int, User]
    liked_post_ids: set[int]
    followed_author_ids: set[int]
    comment_counts: dict[int, int]


def _post_output_context(
    db: Session,
    posts: list[Post],
    user: User | None,
    *,
    hidden_author_ids: set[int] | None = None,
) -> _PostOutputContext:
    post_ids = {int(post.id) for post in posts}
    author_ids = {int(post.user_id) for post in posts}
    if not post_ids:
        return _PostOutputContext({}, set(), set(), {})

    authors = {
        int(author.id): author
        for author in db.query(User).filter(User.id.in_(author_ids)).all()
    }
    viewer_id = int(user.id) if user else None
    if viewer_id:
        liked_post_ids = {
            int(row[0]) for row in db.query(Like.post_id).filter(
                Like.user_id == viewer_id,
                Like.post_id.in_(post_ids),
            ).all()
        }
        followed_author_ids = {
            int(row[0]) for row in db.query(Follow.following_id).filter(
                Follow.follower_id == viewer_id,
                Follow.following_id.in_(author_ids),
            ).all()
        }
        if hidden_author_ids is None:
            hidden_author_ids = _blocked_user_ids(db, viewer_id) | _reported_target_ids(
                db, viewer_id, "user",
            )
        reported_comment_ids = _reported_target_ids(db, viewer_id, "comment")
    else:
        liked_post_ids = set()
        followed_author_ids = set()
        hidden_author_ids = set()
        reported_comment_ids = set()

    comments_query = db.query(
        Comment.post_id,
        func.count(Comment.id),
    ).filter(
        Comment.post_id.in_(post_ids),
        Comment.moderation_status == VISIBLE_MODERATION_STATUS,
    )
    if hidden_author_ids:
        comments_query = comments_query.filter(
            Comment.user_id.notin_(hidden_author_ids),
        )
    if reported_comment_ids:
        comments_query = comments_query.filter(
            Comment.id.notin_(reported_comment_ids),
        )
    comment_counts = {
        int(post_id): int(count)
        for post_id, count in comments_query.group_by(Comment.post_id).all()
    }
    return _PostOutputContext(
        authors=authors,
        liked_post_ids=liked_post_ids,
        followed_author_ids=followed_author_ids,
        comment_counts=comment_counts,
    )


def _post_out(
    p: Post,
    user: User | None,
    db: Session,
    context: _PostOutputContext | None = None,
) -> dict:
    if context is None:
        context = _post_output_context(db, [p], user)
    author = context.authors.get(int(p.user_id))
    # Post.images is stored as JSON text for legacy SQLite compatibility, while
    # the API schema correctly exposes a string array. Build the payload first
    # so Pydantic never tries to interpret the raw JSON string as a list.
    payload = {
        field_name: getattr(p, field_name)
        for field_name in PostOut.model_fields
        if field_name != "images" and hasattr(p, field_name)
    }
    try:
        payload["images"] = json.loads(p.images) if p.images else None
    except (TypeError, ValueError, json.JSONDecodeError):
        payload["images"] = None
    out = PostOut.model_validate(payload).model_dump()
    out["author_name"] = safe_public_display_name(author.username if author else None)
    # Public profile media has no moderation pipeline in the first review
    # release. Keep the private profile avatar usable in account screens while
    # omitting it from community payloads.
    out["author_avatar"] = None
    out["is_liked"] = p.id in context.liked_post_ids
    out["is_following"] = p.user_id in context.followed_author_ids
    out["is_own"] = bool(user) and p.user_id == user.id
    out["comments"] = context.comment_counts.get(int(p.id), 0)
    return out


def _release_visible_post_query(
    db: Session,
    *,
    allow_aggregated: bool = False,
):
    """Apply release-policy visibility at every public post read boundary.

    Client query parameters may narrow the server-approved feed but cannot
    enable content that the active release policy disables. Historical user
    media remains stored for deletion/moderation while being unreachable from
    public lists, details and interaction endpoints.
    """

    query = db.query(Post).filter(
        Post.moderation_status == VISIBLE_MODERATION_STATUS,
    )
    if not settings.COMMUNITY_USER_MEDIA_ENABLED:
        user_post_is_text_only = and_(
            Post.images.is_(None),
            Post.video.is_(None),
            or_(
                Post.content_type.is_(None),
                Post.content_type.notin_(("image", "video")),
            ),
        )
        query = query.filter(or_(
            Post.origin == "aggregated",
            user_post_is_text_only,
        ))

    if not (settings.COMMUNITY_AGGREGATED_CONTENT_ENABLED and allow_aggregated):
        return query.filter(or_(
            Post.origin != "aggregated",
            Post.origin.is_(None),
        ))

    enabled_source_keys = [
        row.key for row in db.query(ContentSource).filter(
            ContentSource.enabled.is_(True),
            ContentSource.rights_status == "allowed",
        ).all()
    ]
    publishable_aggregated_post = and_(
        Post.origin == "aggregated",
        Post.source_key.in_(enabled_source_keys),
        or_(
            Post.content_type != "video",
            and_(
                Post.video_provider == "bilibili",
                Post.video_id.like("BV__________"),
            ),
        ),
    )
    return query.filter(or_(
        Post.origin != "aggregated",
        Post.origin.is_(None),
        publishable_aggregated_post,
    ))


@router.get("/posts", response_model=PostListResponse)
def list_posts(tab: str = "recommend", page: int = Query(default=1, ge=1),
               page_size: int = Query(default=10, ge=1, le=50),
               keyword: str = "",
               allow_aggregated: bool = False,
               user: User | None = Depends(get_optional_current_user), db: Session = Depends(get_db)):
    q = _release_visible_post_query(db, allow_aggregated=allow_aggregated)
    viewer_id = int(user.id) if user else None
    hidden_authors = _blocked_user_ids(db, viewer_id) | _reported_target_ids(
        db, viewer_id, "user"
    )
    if hidden_authors:
        q = q.filter(Post.user_id.notin_(hidden_authors))
    reported_posts = _reported_target_ids(db, viewer_id, "post")
    if reported_posts:
        q = q.filter(Post.id.notin_(reported_posts))
    # 关键词搜索：匹配内容、话题、作者名
    if keyword:
        kw = f"%{keyword}%"
        author_ids = [u.id for u in db.query(User).filter(User.username.like(kw)).all()]
        conds = [
            Post.content.like(kw), Post.content_en.like(kw), Post.topic.like(kw),
            Post.topic_en.like(kw), Post.source_name.like(kw),
        ]
        if author_ids:
            conds.append(Post.user_id.in_(author_ids))
        q = q.filter(or_(*conds))
    if tab == "follow":
        if user is None:
            raise HTTPException(status_code=401, detail="登录后才能查看关注动态")
        following_ids = [f.following_id for f in db.query(Follow).filter(Follow.follower_id == user.id).all()]
        if following_ids:
            q = q.filter(Post.user_id.in_(following_ids))
        else:
            return success({"items": [], "total": 0, "page": page, "page_size": page_size})
    elif tab == "video":
        q = q.filter(Post.content_type == "video").order_by(Post.source_published_at.desc(), Post.created_at.desc())
    elif tab == "latest":
        video_priority = case((Post.content_type == "video", 0), else_=1)
        q = q.order_by(video_priority.asc(), Post.source_published_at.desc(), Post.created_at.desc())
    else:
        video_priority = case((Post.content_type == "video", 0), else_=1)
        q = q.order_by(video_priority.asc(), Post.created_at.desc(), Post.likes.desc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    output_context = _post_output_context(
        db,
        items,
        user,
        hidden_author_ids=hidden_authors,
    )
    return success({
        "items": [_post_out(p, user, db, output_context) for p in items],
        "total": total, "page": page, "page_size": page_size,
    })


@router.post("/posts", response_model=PostResponse)
def create_post(
    data: PostCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    content = validate_public_community_text(data.content)
    topic = validate_public_community_text(data.topic, field_name="话题") if data.topic else None
    if (
        not settings.COMMUNITY_USER_MEDIA_ENABLED
        and (data.images or data.video or data.video_duration is not None)
    ):
        raise BizError("当前版本仅支持发布文字动态", status_code=403)
    images = data.images or []
    if len(images) > 9:
        raise BizError("图片最多上传 9 张")
    if len(set(images)) != len(images):
        raise BizError("请勿重复添加同一张图片")
    if images and data.video:
        raise BizError("图片和视频不能同时发布")
    for image_url in images:
        _media_path_from_url(image_url, user.id, "image")

    video = data.video.strip() if data.video else None
    video_duration: int | None = None
    if video:
        video_path = _media_path_from_url(video, user.id, "video")
        if video_path.suffix.lower() != ".mp4":
            raise BizError("视频未完成兼容处理，请重新上传")
        # Never trust the client duration. The upload may come from web,
        # Android or iOS, but the persisted value is derived from the exact
        # standardized file referenced by the post.
        video_duration = standardized_video_duration(video_path)
    elif data.video_duration is not None:
        raise BizError("视频时长只能随视频提交")

    images_str = json.dumps(images, ensure_ascii=False) if images else None
    source_platform = normalize_platform(platform)
    p = Post(
        user_id=user.id, content=content, images=images_str,
        video=video, video_duration=video_duration,
        topic=topic, origin="user",
        content_type="video" if video else ("image" if images else "text"),
        created_platform=source_platform,
        last_modified_platform=source_platform,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    output_context = _post_output_context(
        db,
        [p],
        user,
        hidden_author_ids=set(),
    )
    return success(_post_out(p, user, db, output_context))


@router.get("/posts/{pid}", response_model=PostResponse)
def post_detail(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _release_visible_post_query(db, allow_aggregated=True).filter(
        Post.id == pid,
    ).first()
    if not p:
        raise BizError("动态不存在", status_code=404)
    hidden_authors = _blocked_user_ids(db, int(user.id)) | _reported_target_ids(
        db, int(user.id), "user"
    )
    if p.user_id in hidden_authors:
        raise BizError("动态不存在", status_code=404)
    if p.id in _reported_target_ids(db, int(user.id), "post"):
        raise BizError("动态不存在", status_code=404)
    output_context = _post_output_context(
        db,
        [p],
        user,
        hidden_author_ids=hidden_authors,
    )
    return success(_post_out(p, user, db, output_context))


def _insert_like_if_missing(
    db: Session,
    *,
    post_id: int,
    user_id: int,
    platform: str,
) -> bool:
    values = {
        "post_id": post_id,
        "user_id": user_id,
        "created_platform": platform,
    }
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        statement = sqlite_insert(Like).values(**values).on_conflict_do_nothing(
            index_elements=["post_id", "user_id"]
        )
    elif dialect == "postgresql":
        statement = postgresql_insert(Like).values(**values).on_conflict_do_nothing(
            index_elements=["post_id", "user_id"]
        )
    else:
        existing = db.query(Like.id).filter(
            Like.post_id == post_id, Like.user_id == user_id
        ).first()
        if existing:
            return False
        try:
            with db.begin_nested():
                result = db.execute(insert(Like).values(**values))
            return result.rowcount == 1
        except IntegrityError:
            return False
    return db.execute(statement).rowcount == 1


def _set_like_state(
    pid: int,
    user_id: int,
    liked: bool,
    db: Session,
    platform: str,
):
    target = _release_visible_post_query(db, allow_aggregated=True).filter(
        Post.id == pid,
    ).first()
    if target is None:
        raise BizError("动态不存在", status_code=404)
    hidden_authors = _blocked_user_ids(db, user_id) | _reported_target_ids(
        db, user_id, "user"
    )
    if (
        target.user_id in hidden_authors
        or pid in _reported_target_ids(db, user_id, "post")
    ):
        raise BizError("动态不存在", status_code=404)

    source_platform = normalize_platform(platform)
    if liked:
        changed = _insert_like_if_missing(
            db,
            post_id=pid,
            user_id=user_id,
            platform=source_platform,
        )
        if changed:
            db.execute(
                update(Post).where(Post.id == pid).values(
                    likes=func.coalesce(Post.likes, 0) + 1,
                    last_modified_platform=source_platform,
                )
            )
    else:
        deleted = db.execute(
            delete(Like).where(Like.post_id == pid, Like.user_id == user_id)
        ).rowcount or 0
        if deleted > 0:
            current_likes = func.coalesce(Post.likes, 0)
            db.execute(
                update(Post).where(Post.id == pid).values(
                    likes=case(
                        (current_likes >= deleted, current_likes - deleted),
                        else_=0,
                    ),
                    last_modified_platform=source_platform,
                )
            )

    db.commit()
    actual_liked = db.query(Like.id).filter(
        Like.post_id == pid, Like.user_id == user_id
    ).first() is not None
    likes = db.query(Post.likes).filter(Post.id == pid).scalar()
    if likes is None:
        raise BizError("动态不存在", status_code=404)
    return success({"liked": actual_liked, "likes": max(0, int(likes))})


@router.post("/posts/{pid}/like")
def toggle_like(
    pid: int,
    data: LikeStateIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    if data is None:
        existing = db.query(Like.id).filter(
            Like.post_id == pid, Like.user_id == user.id
        ).first()
        liked = existing is None
    else:
        liked = bool(data.liked)
    return _set_like_state(pid, user.id, liked, db, platform)


@router.get(
    "/posts/{pid}/comments",
    response_model=CommentListResponse,
    response_model_exclude_none=True,
)
def list_comments(
    pid: int,
    user: User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    visible_post = _release_visible_post_query(db, allow_aggregated=True).filter(
        Post.id == pid,
    ).first()
    if visible_post is None:
        raise BizError("动态不存在", status_code=404)
    query = db.query(Comment).filter(
        Comment.post_id == pid,
        Comment.moderation_status == VISIBLE_MODERATION_STATUS,
    )
    viewer_id = int(user.id) if user else None
    hidden_authors = _blocked_user_ids(db, viewer_id) | _reported_target_ids(
        db, viewer_id, "user"
    )
    if viewer_id and (
        visible_post.user_id in hidden_authors
        or pid in _reported_target_ids(db, viewer_id, "post")
    ):
        raise BizError("动态不存在", status_code=404)
    if hidden_authors:
        query = query.filter(Comment.user_id.notin_(hidden_authors))
    reported_comments = _reported_target_ids(db, viewer_id, "comment")
    if reported_comments:
        query = query.filter(Comment.id.notin_(reported_comments))
    items = query.order_by(
        Comment.created_at.desc()
    ).limit(50).all()
    comment_authors = {
        int(author.id): author
        for author in db.query(User).filter(
            User.id.in_({int(comment.user_id) for comment in items}),
        ).all()
    } if items else {}
    out = []
    for c in items:
        author = comment_authors.get(int(c.user_id))
        # ``post_comments`` is authoritative metadata for create responses.
        # Keep the historical list-item shape unchanged instead of emitting
        # an unnecessary nullable field on every existing comment.
        d = CommentOut.model_validate(c).model_dump(exclude={"post_comments"})
        d["author_name"] = safe_public_display_name(
            author.username if author else None,
        )
        d["is_own"] = bool(user) and c.user_id == user.id
        out.append(d)
    return success(out)


_COMMENT_REQUEST_CONFLICT_MESSAGE = "重复评论请求参数不一致，请重新提交"
_COMMENT_WRITE_CONFLICT_MESSAGE = "评论正在提交，请稍后重试"


def _begin_serialized_comment_transaction(db: Session) -> None:
    """Avoid SQLite read-then-write races; database constraints cover other engines."""

    if db.get_bind().dialect.name != "sqlite":
        return
    try:
        # Authentication already opened a deferred read transaction. Restart it
        # before inspecting the idempotency key so only one SQLite writer can
        # decide whether a comment must be inserted and counted.
        if db.in_transaction():
            db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    except OperationalError as exc:
        db.rollback()
        message = str(exc).lower()
        if "locked" in message or "busy" in message:
            raise BizError(_COMMENT_WRITE_CONFLICT_MESSAGE, status_code=409) from exc
        raise


def _find_comment_by_client_id(
    db: Session,
    user_id: int,
    client_request_id: str,
) -> Comment | None:
    return db.query(Comment).filter(
        Comment.user_id == user_id,
        Comment.client_request_id == client_request_id,
    ).first()


def _same_comment_intent(comment: Comment, *, post_id: int, content: str) -> bool:
    return comment.post_id == post_id and comment.content == content


def _insert_comment_if_missing(
    db: Session,
    *,
    post_id: int,
    user_id: int,
    content: str,
    client_request_id: str | None,
    platform: str,
) -> tuple[Comment, bool]:
    values = {
        "post_id": post_id,
        "user_id": user_id,
        "content": content,
        "client_request_id": client_request_id,
        "created_platform": platform,
    }
    if client_request_id is None:
        comment = Comment(**values)
        db.add(comment)
        db.flush()
        return comment, True

    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        # Targetless conflict handling works with both the partial migrated
        # index and the matching partial index created from model metadata.
        statement = sqlite_insert(Comment).values(**values).on_conflict_do_nothing()
        inserted = db.execute(statement).rowcount == 1
    elif dialect == "postgresql":
        statement = postgresql_insert(Comment).values(**values).on_conflict_do_nothing()
        inserted = db.execute(statement).rowcount == 1
    else:
        try:
            with db.begin_nested():
                inserted = db.execute(insert(Comment).values(**values)).rowcount == 1
        except IntegrityError:
            inserted = False

    comment = _find_comment_by_client_id(db, user_id, client_request_id)
    if comment is None:
        db.rollback()
        raise BizError(_COMMENT_WRITE_CONFLICT_MESSAGE, status_code=409)
    return comment, inserted


def _created_comment_out(comment_id: int, post_id: int, db: Session) -> dict:
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise BizError(_COMMENT_WRITE_CONFLICT_MESSAGE, status_code=409)
    post_comments = int(
        db.query(func.count(Comment.id)).filter(
            Comment.post_id == post_id,
            Comment.moderation_status == VISIBLE_MODERATION_STATUS,
        ).scalar() or 0
    )
    author = db.query(User).filter(User.id == comment.user_id).first()
    result = CommentOut.model_validate(comment).model_dump()
    result["author_name"] = safe_public_display_name(
        author.username if author else None,
    )
    result["post_comments"] = post_comments
    result["is_own"] = True
    return result


@router.post("/posts/{pid}/comments", response_model=CommentResponse)
def create_comment(
    pid: int,
    data: CommentIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    content = validate_public_community_text(data.content, field_name="评论内容")
    user_id = int(user.id)
    client_request_id = str(data.client_request_id or "").strip() or None
    source_platform = normalize_platform(platform)
    _begin_serialized_comment_transaction(db)

    post = _release_visible_post_query(db, allow_aggregated=True).filter(
        Post.id == pid,
    ).first()
    if post is None:
        db.rollback()
        raise BizError("动态不存在", status_code=404)
    hidden_authors = _blocked_user_ids(db, user_id) | _reported_target_ids(
        db, user_id, "user"
    )
    if post.user_id in hidden_authors:
        db.rollback()
        raise BizError("动态不存在", status_code=404)
    if pid in _reported_target_ids(db, user_id, "post"):
        db.rollback()
        raise BizError("动态不存在", status_code=404)

    if client_request_id:
        existing = _find_comment_by_client_id(db, user_id, client_request_id)
        if existing:
            if not _same_comment_intent(existing, post_id=pid, content=content):
                db.rollback()
                raise BizError(_COMMENT_REQUEST_CONFLICT_MESSAGE, status_code=409)
            comment_id = existing.id
            db.commit()
            return success(_created_comment_out(comment_id, pid, db))

    comment, inserted = _insert_comment_if_missing(
        db,
        post_id=pid,
        user_id=user_id,
        content=content,
        client_request_id=client_request_id,
        platform=source_platform,
    )
    if not _same_comment_intent(comment, post_id=pid, content=content):
        db.rollback()
        raise BizError(_COMMENT_REQUEST_CONFLICT_MESSAGE, status_code=409)

    if inserted:
        updated = db.execute(
            update(Post).where(Post.id == pid).values(
                comments=func.coalesce(Post.comments, 0) + 1,
                last_modified_platform=source_platform,
            )
        ).rowcount or 0
        if updated != 1:
            db.rollback()
            raise BizError("动态不存在", status_code=404)

    comment_id = comment.id
    db.commit()
    return success(_created_comment_out(comment_id, pid, db))


def _insert_follow_if_missing(
    db: Session,
    *,
    follower_id: int,
    following_id: int,
    platform: str,
) -> bool:
    values = {
        "follower_id": follower_id,
        "following_id": following_id,
        "created_platform": platform,
    }
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        statement = sqlite_insert(Follow).values(**values).on_conflict_do_nothing(
            index_elements=["follower_id", "following_id"]
        )
    elif dialect == "postgresql":
        statement = postgresql_insert(Follow).values(**values).on_conflict_do_nothing(
            index_elements=["follower_id", "following_id"]
        )
    else:
        existing = db.query(Follow.id).filter(
            Follow.follower_id == follower_id, Follow.following_id == following_id
        ).first()
        if existing:
            return False
        try:
            with db.begin_nested():
                result = db.execute(insert(Follow).values(**values))
            return result.rowcount == 1
        except IntegrityError:
            return False
    return db.execute(statement).rowcount == 1


def _set_follow_state(
    uid: int,
    follower_id: int,
    following: bool,
    db: Session,
    platform: str,
):
    if uid == follower_id:
        raise BizError("不能关注自己")
    if db.query(User.id).filter(User.id == uid).scalar() is None:
        raise BizError("用户不存在", status_code=404)
    if following and db.query(CommunityBlock.id).filter(
        or_(
            and_(
                CommunityBlock.blocker_user_id == follower_id,
                CommunityBlock.blocked_user_id == uid,
            ),
            and_(
                CommunityBlock.blocker_user_id == uid,
                CommunityBlock.blocked_user_id == follower_id,
            ),
        )
    ).first():
        raise BizError("无法关注已屏蔽的用户")

    if following:
        _insert_follow_if_missing(
            db,
            follower_id=follower_id,
            following_id=uid,
            platform=normalize_platform(platform),
        )
    else:
        db.execute(delete(Follow).where(
            Follow.follower_id == follower_id, Follow.following_id == uid
        ))

    db.commit()
    actual_following = db.query(Follow.id).filter(
        Follow.follower_id == follower_id, Follow.following_id == uid
    ).first() is not None
    return success({"following": actual_following})


@router.post("/users/{uid}/follow")
def toggle_follow(
    uid: int,
    data: FollowStateIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    if data is None:
        existing = db.query(Follow.id).filter(
            Follow.follower_id == user.id, Follow.following_id == uid
        ).first()
        following = existing is None
    else:
        following = bool(data.following)
    return _set_follow_state(uid, user.id, following, db, platform)


def _insert_block_if_missing(
    db: Session,
    *,
    blocker_user_id: int,
    blocked_user_id: int,
    platform: str,
) -> None:
    values = {
        "blocker_user_id": blocker_user_id,
        "blocked_user_id": blocked_user_id,
        "created_platform": normalize_platform(platform),
    }
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        db.execute(sqlite_insert(CommunityBlock).values(**values).on_conflict_do_nothing(
            index_elements=["blocker_user_id", "blocked_user_id"],
        ))
    elif dialect == "postgresql":
        db.execute(postgresql_insert(CommunityBlock).values(**values).on_conflict_do_nothing(
            index_elements=["blocker_user_id", "blocked_user_id"],
        ))
    elif db.query(CommunityBlock.id).filter(
        CommunityBlock.blocker_user_id == blocker_user_id,
        CommunityBlock.blocked_user_id == blocked_user_id,
    ).first() is None:
        try:
            with db.begin_nested():
                db.add(CommunityBlock(**values))
                db.flush()
        except IntegrityError:
            pass


@router.post("/users/{uid}/block")
def set_user_block(
    uid: int,
    data: CommunityBlockStateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    user_id = int(user.id)
    if uid == user_id:
        raise BizError("不能屏蔽自己")
    if db.query(User.id).filter(
        User.id == uid,
        User.account_status == "active",
    ).scalar() is None:
        raise BizError("用户不存在", status_code=404)
    if data.blocked:
        _insert_block_if_missing(
            db,
            blocker_user_id=user_id,
            blocked_user_id=uid,
            platform=platform,
        )
        db.execute(delete(Follow).where(or_(
            and_(Follow.follower_id == user_id, Follow.following_id == uid),
            and_(Follow.follower_id == uid, Follow.following_id == user_id),
        )))
    else:
        db.execute(delete(CommunityBlock).where(
            CommunityBlock.blocker_user_id == user_id,
            CommunityBlock.blocked_user_id == uid,
        ))
    db.commit()
    actual = db.query(CommunityBlock.id).filter(
        CommunityBlock.blocker_user_id == user_id,
        CommunityBlock.blocked_user_id == uid,
    ).first() is not None
    return success({"blocked": actual})


_REPORT_WRITE_CONFLICT_MESSAGE = "举报正在提交，请稍后重试"


def _begin_serialized_report_transaction(db: Session) -> None:
    """Serialize SQLite reports; PostgreSQL uses a per-target row lock below."""

    if db.get_bind().dialect.name != "sqlite":
        return
    try:
        if db.in_transaction():
            db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    except OperationalError as exc:
        db.rollback()
        message = str(exc).lower()
        if "locked" in message or "busy" in message:
            raise BizError(_REPORT_WRITE_CONFLICT_MESSAGE, status_code=409) from exc
        raise


def _report_target(
    db: Session,
    target_type: str,
    target_id: int,
    *,
    lock_for_update: bool = False,
):
    if target_type == "post":
        query = db.query(Post).filter(
            Post.id == target_id,
            Post.moderation_status.in_(("visible", "pending_review")),
        )
        target = query.with_for_update().first() if lock_for_update else query.first()
        return target, target.user_id if target else None
    if target_type == "comment":
        query = db.query(Comment).filter(
            Comment.id == target_id,
            Comment.moderation_status.in_(("visible", "pending_review")),
        )
        target = query.with_for_update().first() if lock_for_update else query.first()
        return target, target.user_id if target else None
    query = db.query(User).filter(
        User.id == target_id,
        User.account_status == "active",
    )
    target = query.with_for_update().first() if lock_for_update else query.first()
    return target, target.id if target else None


def _insert_report_if_missing(
    db: Session,
    *,
    reporter_user_id: int,
    data: CommunityReportIn,
    platform: str,
) -> None:
    values = {
        "reporter_user_id": reporter_user_id,
        "target_type": data.target_type,
        "target_id": data.target_id,
        "reason": data.reason,
        "details": data.details.strip() if data.details else None,
        "created_platform": normalize_platform(platform),
    }
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        db.execute(sqlite_insert(CommunityReport).values(**values).on_conflict_do_nothing(
            index_elements=["reporter_user_id", "target_type", "target_id"],
        ))
    elif dialect == "postgresql":
        db.execute(postgresql_insert(CommunityReport).values(**values).on_conflict_do_nothing(
            index_elements=["reporter_user_id", "target_type", "target_id"],
        ))
    elif db.query(CommunityReport.id).filter(
        CommunityReport.reporter_user_id == reporter_user_id,
        CommunityReport.target_type == data.target_type,
        CommunityReport.target_id == data.target_id,
    ).first() is None:
        try:
            with db.begin_nested():
                db.add(CommunityReport(**values))
                db.flush()
        except IntegrityError:
            pass


@router.post("/reports")
def report_community_content(
    data: CommunityReportIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    user_id = int(user.id)
    _begin_serialized_report_transaction(db)
    target, author_id = _report_target(
        db,
        data.target_type,
        data.target_id,
        lock_for_update=True,
    )
    if target is None or author_id is None:
        db.rollback()
        raise BizError("举报对象不存在", status_code=404)
    if int(author_id) == user_id:
        db.rollback()
        raise BizError("不能举报自己的内容或账号")
    _insert_report_if_missing(
        db,
        reporter_user_id=user_id,
        data=data,
        platform=platform,
    )
    report = db.query(CommunityReport).filter(
        CommunityReport.reporter_user_id == user_id,
        CommunityReport.target_type == data.target_type,
        CommunityReport.target_id == data.target_id,
    ).first()
    if report is None:
        db.rollback()
        raise BizError(_REPORT_WRITE_CONFLICT_MESSAGE, status_code=409)

    if data.target_type in {"post", "comment"}:
        pending_count = db.query(func.count(CommunityReport.id)).filter(
            CommunityReport.target_type == data.target_type,
            CommunityReport.target_id == data.target_id,
            CommunityReport.status == "pending",
        ).scalar() or 0
        if pending_count >= AUTO_HIDE_REPORT_THRESHOLD:
            target.moderation_status = "pending_review"
            target.moderation_reason = "multiple_user_reports"
            target.moderated_at = _utcnow()
    db.commit()
    return success({
        "report_id": report.id,
        "status": report.status,
        "hidden_for_reporter": True,
    })


@router.delete("/comments/{comment_id}")
def delete_own_comment(
    comment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if comment is None:
        # DELETE is idempotent and does not disclose whether another user once
        # owned this identifier. Any existing report remains as an audit row
        # whose target is explicitly shown as deleted in the admin queue.
        return success({"deleted": True})
    if comment.user_id != user.id:
        raise BizError("评论不存在", status_code=404)
    post_id = int(comment.post_id)
    db.delete(comment)
    db.flush()
    visible_comment_count = int(db.query(func.count(Comment.id)).filter(
        Comment.post_id == post_id,
        Comment.moderation_status == VISIBLE_MODERATION_STATUS,
    ).scalar() or 0)
    db.execute(update(Post).where(Post.id == post_id).values(
        comments=visible_comment_count,
        last_modified_platform=normalize_platform(platform),
    ))
    db.commit()
    return success({"deleted": True})


@router.delete("/posts/{pid}")
def delete_own_post(
    pid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    post = db.query(Post).filter(Post.id == pid).first()
    if post is None or post.user_id != user.id:
        raise BizError("动态不存在", status_code=404)
    if post.moderation_status != "deleted":
        try:
            media_urls = json.loads(post.images or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            media_urls = []
        media_items = [
            (url, "image") for url in media_urls if isinstance(url, str)
        ]
        if post.video:
            media_items.append((post.video, "video"))
        for media_url, media_kind in media_items:
            try:
                _media_path_from_url(media_url, int(user.id), media_kind).unlink(missing_ok=True)
            except (BizError, OSError):
                pass
        post.content = "[内容已删除]"
        post.images = None
        post.video = None
        post.video_duration = None
        post.topic = None
        post.moderation_status = "deleted"
        post.moderation_reason = "author_deleted"
        post.moderated_at = _utcnow()
        post.last_modified_platform = normalize_platform(platform)
    db.commit()
    return success({"deleted": True})


@router.get("/sources")
def list_content_sources(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(ContentSource).order_by(ContentSource.id.asc()).all()
    return success([
        {
            "key": item.key,
            "name": item.name,
            "kind": item.kind,
            "terms_url": item.terms_url,
            "rights_status": item.rights_status,
            "enabled": item.enabled,
            "reviewed_at": item.reviewed_at,
            "last_success_at": item.last_success_at,
            "available": item.enabled and item.rights_status == "allowed" and not item.last_error,
        }
        for item in items
    ])


@router.get("/ingest/status")
def ingest_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(ContentIngestRun).order_by(ContentIngestRun.id.desc()).first()
    if not item:
        return success(None)
    batch_posts = db.query(Post).filter(Post.publish_batch == item.batch)
    return success({
        "batch": item.batch,
        "target_count": item.target_count,
        "batch_total": batch_posts.count(),
        "batch_videos": batch_posts.filter(Post.content_type == "video").count(),
        "candidate_count": item.candidate_count,
        "published_count": item.published_count,
        "skipped_count": item.skipped_count,
        "failed_count": item.failed_count,
        "status": item.status,
        "started_at": item.started_at,
        "finished_at": item.finished_at,
    })
