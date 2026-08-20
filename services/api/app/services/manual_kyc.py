import base64
import hashlib
import json
import os
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.orm import Session

from app.config import settings
from app.kyc_schemas import ManualKycSubmitIn
from app.models import KycApplication, User
from app.security import ApiError, ensure_verified_email
from app.services.internal_modules import create_notification


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cipher() -> AESGCM:
    source = settings.KYC_ENCRYPTION_KEY or settings.SECRET_KEY
    return AESGCM(hashlib.sha256(f"wod-kyc-v1:{source}".encode()).digest())


def _encrypt(details: dict[str, str | None]) -> str:
    nonce = os.urandom(12)
    payload = json.dumps(details, ensure_ascii=False, separators=(",", ":")).encode()
    encrypted = _cipher().encrypt(nonce, payload, b"wod-manual-kyc-v1")
    return base64.urlsafe_b64encode(nonce + encrypted).decode()


def _decrypt(value: str) -> dict[str, str | None]:
    try:
        raw = base64.urlsafe_b64decode(value.encode())
        payload = _cipher().decrypt(raw[:12], raw[12:], b"wod-manual-kyc-v1")
        result = json.loads(payload)
        if not isinstance(result, dict):
            raise ValueError("invalid identity payload")
        return result
    except Exception as exc:
        raise ApiError("KYC_DETAILS_UNAVAILABLE", "实名认证信息无法解密，请检查加密密钥", 500) from exc


def provider_descriptor() -> dict:
    return {
        "kind": "kyc",
        "provider": "manual_review",
        "status": "configured",
        "configured": True,
        "capabilities": ["encrypted_identity", "manual_review", "audit_status"],
        "reason": None,
    }


def application_out(
    row: KycApplication,
    *,
    applicant: User | None = None,
    reveal_identifier: bool = False,
) -> dict:
    details = _decrypt(row.subject_details_encrypted) if row.subject_details_encrypted else {}
    identifier = details.get("identifier_number")
    masked = None
    if identifier:
        masked = identifier if reveal_identifier else f"****{row.subject_identifier_last4}"
    data = {
        "id": row.id,
        "status": row.status,
        "provider": row.provider,
        "verification_type": row.verification_type,
        "country_code": row.country_code,
        "subject": {
            "legal_name": details.get("legal_name"),
            "identifier_type": details.get("identifier_type"),
            "identifier_number": masked,
            "representative_name": details.get("representative_name"),
        } if details else None,
        "review_note": row.review_note,
        "submitted_at": row.submitted_at,
        "reviewed_at": row.reviewed_at,
        "declaration_accepted_at": row.declaration_accepted_at,
        "expires_at": row.expires_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "version": row.version,
    }
    if applicant is not None:
        data["applicant"] = {
            "id": applicant.id,
            "display_name": applicant.display_name,
            "email": applicant.email,
            "phone": applicant.phone,
            "role": applicant.role,
        }
    return data


def snapshot(db: Session, user: User) -> dict:
    row = db.query(KycApplication).filter(KycApplication.user_id == user.id).first()
    return {
        "status": row.status if row else "unverified",
        "application": application_out(row) if row else None,
        "provider": provider_descriptor(),
    }


def submit(db: Session, user: User, data: ManualKycSubmitIn) -> KycApplication:
    ensure_verified_email(user)
    row = db.query(KycApplication).filter(
        KycApplication.user_id == user.id
    ).with_for_update().first()
    if row is not None and row.status in ("pending", "approved"):
        raise ApiError("KYC_ALREADY_ACTIVE", "当前实名认证正在审核或已经通过", 409)
    details = {
        "legal_name": data.legal_name.strip(),
        "identifier_type": data.identifier_type,
        "identifier_number": data.identifier_number.upper(),
        "representative_name": data.representative_name.strip() if data.representative_name else None,
    }
    now = _now()
    if row is None:
        row = KycApplication(user_id=user.id)
        db.add(row)
    row.status = "pending"
    row.provider = "manual_review"
    row.provider_reference = None
    row.verification_type = data.verification_type
    row.country_code = data.country_code
    row.subject_details_encrypted = _encrypt(details)
    row.subject_identifier_last4 = data.identifier_number[-4:].upper()
    row.declaration_accepted_at = now
    row.review_note = None
    row.reviewed_by_user_id = None
    row.submitted_at = now
    row.reviewed_at = None
    row.expires_at = None
    if row.id is not None:
        row.version += 1
    create_notification(
        db,
        user_id=user.id,
        category="review",
        title="实名认证已提交",
        body="平台管理员将核对你的实名信息，审核结果会通过站内通知发送。",
        action_path="/account/verification",
    )
    db.commit()
    db.refresh(row)
    return row


def list_pending(db: Session, *, status: str | None = None) -> list[tuple[KycApplication, User]]:
    query = db.query(KycApplication, User).join(User, User.id == KycApplication.user_id)
    if status:
        query = query.filter(KycApplication.status == status)
    return query.order_by(KycApplication.updated_at.desc(), KycApplication.id.desc()).limit(200).all()


def review(
    db: Session,
    admin: User,
    application_id: int,
    *,
    version: int,
    approved: bool,
    note: str | None,
) -> KycApplication:
    row = db.query(KycApplication).filter(
        KycApplication.id == application_id
    ).with_for_update().first()
    if row is None:
        raise ApiError("KYC_APPLICATION_NOT_FOUND", "实名认证申请不存在", 404)
    if row.version != version:
        raise ApiError("KYC_VERSION_CONFLICT", "实名认证记录已更新，请刷新后重试", 409)
    if row.status != "pending":
        raise ApiError("KYC_NOT_REVIEWABLE", "只有待审核实名认证可以处理", 409)
    row.status = "approved" if approved else "rejected"
    row.review_note = note.strip() if note else None
    row.reviewed_by_user_id = admin.id
    row.reviewed_at = _now()
    row.version += 1
    create_notification(
        db,
        user_id=row.user_id,
        category="review",
        title="实名认证已通过" if approved else "实名认证需要重新提交",
        body=(note.strip() if note else "实名认证审核已经完成。"),
        action_path="/account/verification",
    )
    db.commit()
    db.refresh(row)
    return row


def approved_for_user(db: Session, user_id: int) -> bool:
    return db.query(KycApplication.id).filter(
        KycApplication.user_id == user_id,
        KycApplication.status == "approved",
    ).first() is not None
