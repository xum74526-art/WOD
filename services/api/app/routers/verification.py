import asyncio
import io
import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.sensitive import mask_id_card, protect, reveal, sensitive_capability_enabled
from app.db.session import get_db
from app.models.user import User
from app.models.verification import Verification
from app.schemas.verification import VerificationIn
from app.services.id_card_ocr import (
    OCR_STATUS_ERROR,
    OCR_STATUS_MATCHED,
    OCR_STATUS_NOT_STARTED,
    OCR_STATUS_PROCESSING,
    OCR_STATUS_REVIEW_REQUIRED,
    OCR_STATUS_UNAVAILABLE,
    OcrPrecheckResult,
    run_identity_precheck,
)
from app.utils.id_card_util import validate_id_card, extract_gender, extract_birthday
from app.utils.response import BizError, success

router = APIRouter(prefix="/api/verification", tags=["verification"])

UPLOAD_ROOT = Path(settings.UPLOAD_ROOT).expanduser().resolve() if settings.UPLOAD_ROOT else Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_DIR = UPLOAD_ROOT / "id_cards"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _require_ocr_security() -> None:
    if settings.ID_OCR_ENABLED and not sensitive_capability_enabled(True):
        raise BizError("本地文字识别的敏感数据安全配置未完成", status_code=503)


def _normalized_id_photo(content: bytes) -> tuple[str, bytes]:
    """Validate and re-encode a single-frame image without EXIF/metadata."""
    if content.startswith(b"\xff\xd8\xff"):
        expected_format, extension = "JPEG", "jpg"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        expected_format, extension = "PNG", "png"
    elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        expected_format, extension = "WEBP", "webp"
    else:
        raise BizError("仅支持真实的 JPG、PNG 或 WebP 图片")

    try:
        with Image.open(io.BytesIO(content)) as image:
            actual_format = (image.format or "").upper()
            if getattr(image, "n_frames", 1) != 1:
                raise BizError("身份证图片不能是动画图片")
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > settings.ID_OCR_MAX_PIXELS:
                raise BizError("身份证图片像素尺寸过大")
            image.verify()
        if actual_format != expected_format:
            raise BizError("身份证图片签名与实际格式不一致")
        with Image.open(io.BytesIO(content)) as image:
            normalized = ImageOps.exif_transpose(image)
            normalized.load()
            if "A" in normalized.getbands():
                rgba = normalized.convert("RGBA")
                canvas = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                normalized = Image.alpha_composite(canvas, rgba).convert("RGB")
            else:
                normalized = normalized.convert("RGB")
            output = io.BytesIO()
            if expected_format == "JPEG":
                normalized.save(output, format="JPEG", quality=92, optimize=True)
            elif expected_format == "PNG":
                normalized.save(output, format="PNG", optimize=True)
            else:
                normalized.save(output, format="WEBP", quality=92, method=4)
    except BizError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise BizError("身份证图片已损坏或格式无效")
    return extension, output.getvalue()


def _atomic_write_id_photo(content: bytes, destination: Path, user_id: int) -> None:
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".id_{user_id}_", suffix=".tmp",
            dir=UPLOAD_DIR, delete=False,
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


def _clear_id_photos(verification: Verification) -> None:
    """Drop photos when the identity fields they were meant to prove change."""
    for side in ("front", "back"):
        for extension in ("jpg", "png", "webp"):
            old_path = UPLOAD_DIR / f"id_{side}_{verification.user_id}.{extension}"
            if old_path.is_file():
                old_path.unlink()
    verification.front_photo = None
    verification.back_photo = None
    _reset_ocr(verification)


def _reset_ocr(verification: Verification) -> None:
    verification.ocr_status = OCR_STATUS_NOT_STARTED
    verification.ocr_summary = None
    verification.ocr_error_code = None
    verification.ocr_updated_at = None
    verification.ocr_input_token = secrets.token_hex(32)


def _ocr_message(status: str) -> str:
    return {
        OCR_STATUS_NOT_STARTED: "请上传身份证正反面后进行资料匹配",
        OCR_STATUS_PROCESSING: "正在进行本地文字识别",
        OCR_STATUS_MATCHED: "资料匹配，待人工确认",
        OCR_STATUS_REVIEW_REQUIRED: "证件文字与填写资料未完全匹配，请人工复核",
        OCR_STATUS_ERROR: "文字识别暂未完成，请重新上传清晰照片",
        OCR_STATUS_UNAVAILABLE: "本地文字识别暂不可用，待人工处理",
    }.get(status, "待人工确认")


def _decoded_ocr_detail(verification: Verification) -> dict:
    if not verification.ocr_summary:
        return {}
    try:
        value = json.loads(reveal(verification.ocr_summary))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def ocr_public_summary(verification: Verification) -> dict:
    """Return non-sensitive OCR comparison data shared by user/admin APIs."""
    status = verification.ocr_status or OCR_STATUS_NOT_STARTED
    detail = _decoded_ocr_detail(verification)
    raw_summary = detail.get("summary")
    summary = None
    if isinstance(raw_summary, dict):
        keys = (
            "name_match", "id_number_match", "birth_date_match",
            "gender_match", "validity_match",
        )
        summary = {key: bool(raw_summary.get(key, False)) for key in keys}
    validity = detail.get("validity")
    if not isinstance(validity, dict):
        validity = None
    elif validity:
        validity = {
            "valid_from": validity.get("valid_from"),
            "valid_until": validity.get("valid_until"),
            "long_term": bool(validity.get("long_term", False)),
        }
    return {
        "ocr_status": status,
        "ocr_summary": summary,
        "ocr_error_code": verification.ocr_error_code,
        "ocr_updated_at": verification.ocr_updated_at,
        "ocr_message": _ocr_message(status),
        "ocr_validity": validity,
    }


def _ocr_result_values(result: OcrPrecheckResult) -> dict:
    detail = {
        "summary": result.summary,
        "validity": {
            "valid_from": result.valid_from,
            "valid_until": result.valid_until,
            "long_term": result.long_term,
        } if result.valid_from else None,
    }
    return {
        "ocr_status": result.status,
        "ocr_error_code": result.error_code,
        "ocr_summary": protect(json.dumps(
            detail, ensure_ascii=False, separators=(",", ":"),
        )),
        "ocr_updated_at": datetime.now(timezone.utc).replace(tzinfo=None),
    }


def _store_ocr_result_if_current(
    db: Session,
    verification_id: int,
    input_token: str,
    result: OcrPrecheckResult,
) -> bool:
    """Atomically reject a result produced for superseded identity/photos."""
    if not input_token:
        return False
    updated = db.query(Verification).filter(
        Verification.id == verification_id,
        Verification.ocr_input_token == input_token,
    ).update(_ocr_result_values(result), synchronize_session=False)
    db.commit()
    db.expire_all()
    return updated == 1


@router.get("")
def get_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    v = db.query(Verification).filter(Verification.user_id == user.id).first()
    if not v:
        return success({
            "status": "unverified", "real_name": None, "id_card_masked": None,
            "consent_recorded": False,
            "ocr_status": OCR_STATUS_NOT_STARTED,
            "ocr_summary": None,
            "ocr_error_code": None,
            "ocr_updated_at": None,
            "ocr_message": _ocr_message(OCR_STATUS_NOT_STARTED),
            "ocr_validity": None,
        })
    payload = {
        "status": v.status,
        "real_name": v.real_name,
        "id_card_masked": mask_id_card(v.id_card),
        "reject_reason": v.reject_reason,
        "front_photo_uploaded": bool(v.front_photo),
        "back_photo_uploaded": bool(v.back_photo),
        "consent_recorded": bool(v.consent_at),
        "created_at": v.created_at,
    }
    payload.update(ocr_public_summary(v))
    return success(payload)


@router.post("")
def submit(data: VerificationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_ocr_security()
    if data.sensitive_consent is not True:
        raise BizError("请先单独同意身份证敏感信息用于本地文字识别和人工审核", status_code=400)
    # 1. 姓名：至少2个中文字符
    if not re.match(r'^[\u4e00-\u9fa5]{2,10}$', data.real_name):
        raise BizError("姓名须为2-10位中文")
    # 2. 身份证号校验
    id_card = data.id_card.strip().upper()
    valid, err = validate_id_card(id_card)
    if not valid:
        raise BizError(err)
    # 3. 已认证不允许重复
    existing = db.query(Verification).filter(Verification.user_id == user.id).first()
    if existing and existing.status == "verified":
        raise BizError("您已通过实名认证")
    # 4. 只创建待审核申请。没有真实核验服务时绝不模拟“已认证”。
    gender = extract_gender(id_card)
    consent_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if existing:
        identity_changed = existing.real_name != data.real_name or reveal(existing.id_card) != id_card
        if identity_changed:
            _clear_id_photos(existing)
        else:
            # A resubmission is a new consent/review generation even if the
            # text is unchanged.  Any in-flight result belongs to the old one.
            _reset_ocr(existing)
        existing.real_name = data.real_name
        existing.id_card = protect(id_card)
        existing.status = "pending"
        existing.reject_reason = None
        existing.consent_at = consent_at
    else:
        v = Verification(
            user_id=user.id, real_name=data.real_name, id_card=protect(id_card),
            status="pending", ocr_status=OCR_STATUS_NOT_STARTED,
            ocr_input_token=secrets.token_hex(32),
            consent_at=consent_at,
        )
        db.add(v)
    db.commit()
    current = existing or v
    payload = {
        "status": "pending",
        "real_name": data.real_name,
        "id_card_masked": mask_id_card(protect(id_card) or ""),
        "gender": gender,
        "birthday": extract_birthday(id_card),
        "consent_recorded": True,
    }
    payload.update(ocr_public_summary(current))
    return success(payload)


@router.post("/upload")
async def upload_id_photo(
    front: UploadFile | None = File(None),
    back: UploadFile | None = File(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传身份证照片。文件保存在私有目录，不提供公开静态 URL。"""
    if not front and not back:
        raise BizError("请选择身份证照片")
    _require_ocr_security()
    v = db.query(Verification).filter(Verification.user_id == user.id).first()
    if not v:
        raise BizError("请先提交认证信息")
    if v.status == "verified":
        raise BizError("您已通过实名认证")
    if not v.consent_at:
        raise BizError("请重新提交认证信息并单独同意敏感信息处理后再上传", status_code=400)

    async def prepare_one(upload: UploadFile, side: str) -> tuple[str, bytes, str]:
        content = await upload.read(settings.ID_PHOTO_MAX_BYTES + 1)
        if not content:
            raise BizError("请选择身份证照片")
        if len(content) > settings.ID_PHOTO_MAX_BYTES:
            raise BizError("单张身份证照片不能超过 5MB")
        extension, normalized = _normalized_id_photo(content)
        return side, normalized, f"id_{side}_{user.id}.{extension}"

    # Validate every supplied side before writing either one. A forged back
    # image therefore cannot leave a newly accepted front image behind.
    prepared: list[tuple[str, bytes, str]] = []
    if front:
        prepared.append(await prepare_one(front, "front"))
    if back:
        prepared.append(await prepare_one(back, "back"))

    _reset_ocr(v)
    for side, content, filename in prepared:
        destination = UPLOAD_DIR / filename
        _atomic_write_id_photo(content, destination, user.id)
        for old_extension in ("jpg", "png", "webp"):
            old_path = UPLOAD_DIR / f"id_{side}_{user.id}.{old_extension}"
            if old_path != destination and old_path.is_file():
                old_path.unlink()
        if side == "front":
            v.front_photo = filename
        else:
            v.back_photo = filename
    db.commit()

    if v.front_photo and v.back_photo:
        ocr_input_token = v.ocr_input_token or ""
        if not settings.ID_OCR_ENABLED:
            _store_ocr_result_if_current(db, v.id, ocr_input_token, OcrPrecheckResult(
                status=OCR_STATUS_UNAVAILABLE,
                summary=None,
                error_code="disabled",
            ))
        else:
            v.ocr_status = OCR_STATUS_PROCESSING
            v.ocr_error_code = None
            v.ocr_updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
            front_path = (UPLOAD_DIR / Path(v.front_photo).name).resolve()
            back_path = (UPLOAD_DIR / Path(v.back_photo).name).resolve()
            try:
                result = await asyncio.to_thread(
                    run_identity_precheck,
                    front_path,
                    back_path,
                    real_name=v.real_name,
                    id_number=reveal(v.id_card),
                )
            except Exception:
                # No OCR text or subprocess diagnostics are logged or exposed.
                result = OcrPrecheckResult(
                    status=OCR_STATUS_ERROR,
                    summary=None,
                    error_code="internal_error",
                )
            _store_ocr_result_if_current(db, v.id, ocr_input_token, result)
        v = db.query(Verification).filter(Verification.id == v.id).one()

    payload = {
        "front_photo_uploaded": bool(v.front_photo),
        "back_photo_uploaded": bool(v.back_photo),
        "status": v.status,
        "consent_recorded": bool(v.consent_at),
    }
    payload.update(ocr_public_summary(v))
    return success(payload)
