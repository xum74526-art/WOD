import io
import os
import re
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.security import verify_password, hash_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import ChangePasswordIn, ProfileUpdateIn, UserOut
from app.utils.response import BizError, success

router = APIRouter(prefix="/api/user", tags=["user"])

# The upload root remains private. Only files in this dedicated avatar child
# directory are exposed, through the tightly validated route below. Identity
# documents under uploads/id_cards are never mounted as static files.
UPLOAD_ROOT = Path(settings.UPLOAD_ROOT).expanduser().resolve() if settings.UPLOAD_ROOT else Path(__file__).resolve().parents[2] / "uploads"
AVATAR_DIR = UPLOAD_ROOT / "avatars"
AVATAR_DIR.mkdir(parents=True, exist_ok=True)
AVATAR_FILENAME_RE = re.compile(r"^avatar_(\d+)\.(jpg|png|webp)$")
AVATAR_MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def _verified_avatar_extension(content: bytes) -> str:
    """Return a trusted extension after magic-byte and decoder verification."""
    if content.startswith(b"\xff\xd8\xff"):
        expected_format, extension = "JPEG", "jpg"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        expected_format, extension = "PNG", "png"
    elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        expected_format, extension = "WEBP", "webp"
    else:
        raise BizError("仅支持真实的 JPG、PNG 或 WebP 头像")

    try:
        with Image.open(io.BytesIO(content)) as image:
            actual_format = (image.format or "").upper()
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise BizError("头像图片已损坏或格式无效")
    if actual_format != expected_format:
        raise BizError("头像图片签名与实际格式不一致")
    return extension


@router.get("/profile")
def profile(user: User = Depends(get_current_user)):
    return success(UserOut.model_validate(user).model_dump())


@router.put("/profile")
def update_profile(data: ProfileUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if data.avatar is not None and data.avatar != user.avatar:
        # Prevent temporary local paths or arbitrary remote URLs from being
        # persisted. The authenticated upload endpoint owns avatar changes.
        raise BizError("请通过头像上传功能修改头像")
    if data.phone is not None and data.phone != user.phone:
        # SMS verification is not connected in the test build. Never let a
        # profile edit silently replace a login identifier. Kai-only accounts
        # will use a future, dedicated verified binding flow.
        raise BizError("修改手机号需先完成验证码验证")
    if data.username:
        user.username = data.username
    db.commit()
    db.refresh(user)
    return success(UserOut.model_validate(user).model_dump())


@router.post("/avatar")
async def upload_avatar(
    avatar: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persist one authenticated user's public avatar (max 2 MiB)."""
    content = await avatar.read(settings.AVATAR_MAX_BYTES + 1)
    if not content:
        raise BizError("请选择头像图片")
    if len(content) > settings.AVATAR_MAX_BYTES:
        raise BizError("头像图片不能超过 2MB")

    extension = _verified_avatar_extension(content)
    filename = f"avatar_{user.id}.{extension}"
    destination = AVATAR_DIR / filename
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".avatar_{user.id}_", suffix=".tmp",
            dir=AVATAR_DIR, delete=False,
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

    # Remove an older avatar stored under another supported extension.
    for old_extension in AVATAR_MEDIA_TYPES:
        old_path = AVATAR_DIR / f"avatar_{user.id}.{old_extension}"
        if old_path != destination and old_path.is_file():
            old_path.unlink()

    # API-relative URL: H5 resolves it below /api, while Android resolves it
    # below the configured App API base. A version query avoids stale
    # native image caches after replacing the deterministic user-id filename.
    user.avatar = f"/user/avatars/{filename}?v={time.time_ns()}"
    db.commit()
    db.refresh(user)
    return success({"avatar": user.avatar})


@router.get("/avatars/{filename}", include_in_schema=False)
def public_avatar(filename: str):
    """Serve only validated public avatar names, never the upload root."""
    match = AVATAR_FILENAME_RE.fullmatch(filename)
    if not match:
        raise HTTPException(status_code=404, detail="头像不存在")
    path = AVATAR_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="头像不存在")
    extension = match.group(2)
    return FileResponse(
        path,
        media_type=AVATAR_MEDIA_TYPES[extension],
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/role/switch")
def switch_role(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.supplier_status != "approved":
        raise BizError("您尚未通过商家审核，无法切换角色")
    if user.role == "personal":
        user.role = "supplier"
    else:
        user.role = "personal"
    db.commit()
    return success({"role": user.role})


@router.get("/rebate")
def rebate_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """消费返佣概览"""
    from app.services.rebate_settle import get_rebate_summary
    return success(get_rebate_summary(user.id, db))


@router.post("/password")
def change_password(data: ChangePasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(data.old_password, user.password):
        raise BizError("原密码错误")
    user.password = hash_password(data.new_password)
    db.commit()
    return success({"changed": True})
