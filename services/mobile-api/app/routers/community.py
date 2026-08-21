import io
import json
import os
import re
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy import case, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.community import Comment, ContentIngestRun, ContentSource, Follow, Like, Post
from app.models.user import User
from app.schemas.community import CommentIn, CommentOut, PostCreateIn, PostOut
from app.utils.response import BizError, success

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
COMMUNITY_FILENAME_RE = re.compile(r"^([0-9a-f]{32})\.(jpg|png|webp|mp4|webm)$")
COMMUNITY_MEDIA_URL_RE = re.compile(
    r"^/uploads/community/([1-9]\d*)/([0-9a-f]{32})\.(jpg|png|webp|mp4|webm)$"
)
IMAGE_EXTENSIONS = {"jpg", "png", "webp"}
VIDEO_EXTENSIONS = {"mp4", "webm"}
MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "mp4": "video/mp4",
    "webm": "video/webm",
}


def _requested_extension(filename: str | None) -> str:
    extension = Path(filename or "").suffix.lower().lstrip(".")
    if extension == "jpeg":
        extension = "jpg"
    if extension not in MEDIA_TYPES:
        raise BizError("仅支持 JPG、PNG、WebP、MP4 或 WebM")
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

    # ISO Base Media File Format: MP4 stores the ftyp box at byte offset 4.
    if len(content) >= 12 and content[4:8] == b"ftyp":
        return "mp4"
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
):
    requested_extension = _requested_extension(media.filename)
    is_image = requested_extension in IMAGE_EXTENSIONS
    max_bytes = settings.COMMUNITY_IMAGE_MAX_BYTES if is_image else settings.COMMUNITY_VIDEO_MAX_BYTES
    content = await media.read(max_bytes + 1)
    if not content:
        raise BizError("请选择要上传的社区媒体")
    if len(content) > max_bytes:
        raise BizError("社区图片不能超过 5MB" if is_image else "社区视频不能超过 50MB")

    detected_extension = _verified_media_extension(content, "image" if is_image else "video")
    if detected_extension != requested_extension:
        raise BizError("文件扩展名与实际格式不一致")

    user_dir = COMMUNITY_DIR / str(user.id)
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
        "url": f"/uploads/community/{user.id}/{filename}",
        "kind": "image" if is_image else "video",
        "content_type": MEDIA_TYPES[detected_extension],
        "size": len(content),
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
def public_community_media(user_id: int, filename: str, request: Request):
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


def _post_out(p: Post, user: User, db: Session) -> dict:
    u = db.query(User).filter(User.id == p.user_id).first()
    is_liked = db.query(Like).filter(Like.post_id == p.id, Like.user_id == user.id).first() is not None
    is_following = db.query(Follow).filter(Follow.follower_id == user.id, Follow.following_id == p.user_id).first() is not None
    # 用真实评论数替代种子生成时的随机数
    actual_comments = db.query(Comment).filter(Comment.post_id == p.id).count()
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
    out["author_name"] = u.username if u else "匿名"
    out["author_avatar"] = u.avatar if u else None
    out["is_liked"] = is_liked
    out["is_following"] = is_following
    out["is_own"] = (p.user_id == user.id)
    out["comments"] = actual_comments
    return out


@router.get("/posts")
def list_posts(tab: str = "recommend", page: int = Query(default=1, ge=1),
               page_size: int = Query(default=10, ge=1, le=50),
               keyword: str = "",
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Post)
    # 外部来源一旦停用或授权状态变更，聚合内容立即停止展示；用户内容和站内行情不受影响。
    enabled_source_keys = [
        row.key for row in db.query(ContentSource).filter(
            ContentSource.enabled.is_(True), ContentSource.rights_status == "allowed"
        ).all()
    ]
    q = q.filter(or_(Post.origin != "aggregated", Post.origin.is_(None), Post.source_key.in_(enabled_source_keys)))
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
    return success({
        "items": [_post_out(p, user, db) for p in items],
        "total": total, "page": page, "page_size": page_size,
    })


@router.post("/posts")
def create_post(data: PostCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not data.content or not data.content.strip():
        raise BizError("内容不能为空")
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
    if video:
        _media_path_from_url(video, user.id, "video")
        if not data.video_duration or data.video_duration <= 0:
            raise BizError("视频时长无效")
    elif data.video_duration is not None:
        raise BizError("视频时长只能随视频提交")

    images_str = json.dumps(images, ensure_ascii=False) if images else None
    p = Post(
        user_id=user.id, content=data.content, images=images_str,
        video=video, video_duration=data.video_duration if video else None,
        topic=data.topic, origin="user",
        content_type="video" if video else ("image" if images else "text"),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return success(_post_out(p, user, db))


@router.get("/posts/{pid}")
def post_detail(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(Post).filter(Post.id == pid).first()
    if not p:
        raise BizError("动态不存在", status_code=404)
    return success(_post_out(p, user, db))


@router.post("/posts/{pid}/like")
def toggle_like(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(Post).filter(Post.id == pid).first()
    if not p:
        raise BizError("动态不存在", status_code=404)
    existing = db.query(Like).filter(Like.post_id == pid, Like.user_id == user.id).first()
    if existing:
        db.delete(existing)
        p.likes = max(0, p.likes - 1)
        db.commit()
        return success({"liked": False, "likes": p.likes})
    else:
        db.add(Like(post_id=pid, user_id=user.id))
        p.likes = p.likes + 1
        db.commit()
        return success({"liked": True, "likes": p.likes})


@router.get("/posts/{pid}/comments")
def list_comments(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Comment).filter(Comment.post_id == pid).order_by(
        Comment.created_at.desc()
    ).limit(50).all()
    out = []
    for c in items:
        u = db.query(User).filter(User.id == c.user_id).first()
        d = CommentOut.model_validate(c).model_dump()
        d["author_name"] = u.username if u else "匿名"
        out.append(d)
    return success(out)


@router.post("/posts/{pid}/comments")
def create_comment(pid: int, data: CommentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(Post).filter(Post.id == pid).first()
    if not p:
        raise BizError("动态不存在", status_code=404)
    if not data.content:
        raise BizError("评论内容不能为空")
    c = Comment(post_id=pid, user_id=user.id, content=data.content)
    db.add(c)
    p.comments = p.comments + 1
    db.commit()
    db.refresh(c)
    u = db.query(User).filter(User.id == c.user_id).first()
    d = CommentOut.model_validate(c).model_dump()
    d["author_name"] = u.username if u else "匿名"
    return success(d)


@router.post("/users/{uid}/follow")
def toggle_follow(uid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if uid == user.id:
        raise BizError("不能关注自己")
    target = db.query(User).filter(User.id == uid).first()
    if not target:
        raise BizError("用户不存在", status_code=404)
    existing = db.query(Follow).filter(Follow.follower_id == user.id, Follow.following_id == uid).first()
    if existing:
        db.delete(existing)
        db.commit()
        return success({"following": False})
    else:
        db.add(Follow(follower_id=user.id, following_id=uid))
        db.commit()
        return success({"following": True})


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
