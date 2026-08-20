from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import SupplierApplication, SupplierApplicationEvent, User
from app.schemas import SupplierApplicationIn
from app.security import ApiError, ensure_verified_email
from app.services.internal_modules import create_notification
from app.services.manual_kyc import approved_for_user


def _now() -> datetime:
    return datetime.now(timezone.utc)


def application_out(
    row: SupplierApplication,
    *,
    applicant: User | None = None,
    include_reviewer: bool = False,
) -> dict:
    data = {
        "id": row.id,
        "company_name": row.company_name,
        "contact_name": row.contact_name,
        "contact_phone": row.contact_phone,
        "region": row.region,
        "description": row.description,
        "status": row.status,
        "review_note": row.review_note,
        "reviewed_at": row.reviewed_at,
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
            "status": applicant.status,
            "created_at": applicant.created_at,
        }
    if include_reviewer:
        data["reviewed_by"] = row.reviewed_by
    return data


def event_out(row: SupplierApplicationEvent) -> dict:
    return {
        "id": row.id,
        "actor_user_id": row.actor_user_id,
        "actor_role": row.actor_role,
        "event_type": row.event_type,
        "from_status": row.from_status,
        "to_status": row.to_status,
        "note": row.note,
        "payload": row.payload or {},
        "created_at": row.created_at,
    }


def _add_event(
    db: Session,
    application: SupplierApplication,
    actor: User,
    *,
    event_type: str,
    from_status: str | None,
    to_status: str,
    note: str | None = None,
    payload: dict | None = None,
) -> None:
    db.add(SupplierApplicationEvent(
        application_id=application.id,
        actor_user_id=actor.id,
        actor_role=actor.role,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        note=note,
        payload=payload or {},
    ))


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(
            "SUPPLIER_APPLICATION_CONFLICT",
            "商家申请数据发生冲突，请刷新后重试",
            409,
        ) from exc


def submit_application(
    db: Session,
    user: User,
    data: SupplierApplicationIn,
) -> SupplierApplication:
    ensure_verified_email(user)
    row = db.query(SupplierApplication).filter(
        SupplierApplication.user_id == user.id
    ).with_for_update().first()
    if row is not None and row.status in ("pending", "approved"):
        raise ApiError("APPLICATION_EXISTS", "已有待审核或已通过的商家申请", 409)

    if row is None:
        row = SupplierApplication(
            user_id=user.id,
            company_name=data.company_name,
            contact_name=data.contact_name,
            contact_phone=data.contact_phone,
            region=data.region,
            description=data.description,
            status="pending",
            version=1,
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise ApiError("APPLICATION_EXISTS", "已有商家申请", 409) from exc
        _add_event(
            db,
            row,
            user,
            event_type="submitted",
            from_status=None,
            to_status="pending",
        )
    else:
        previous = row.status
        row.company_name = data.company_name
        row.contact_name = data.contact_name
        row.contact_phone = data.contact_phone
        row.region = data.region
        row.description = data.description
        row.status = "pending"
        row.review_note = None
        row.reviewed_by = None
        row.reviewed_at = None
        row.version += 1
        _add_event(
            db,
            row,
            user,
            event_type="resubmitted",
            from_status=previous,
            to_status="pending",
        )
    _commit(db)
    db.refresh(row)
    return row


def list_applications(
    db: Session,
    *,
    page: int,
    page_size: int,
    status: str | None,
    search: str | None,
) -> tuple[list[tuple[SupplierApplication, User]], int]:
    query = db.query(SupplierApplication, User).join(
        User,
        User.id == SupplierApplication.user_id,
    )
    if status:
        query = query.filter(SupplierApplication.status == status)
    if search:
        value = f"%{search.strip()}%"
        query = query.filter(or_(
            SupplierApplication.company_name.ilike(value),
            SupplierApplication.contact_name.ilike(value),
            User.display_name.ilike(value),
            User.email.ilike(value),
        ))
    total = query.count()
    rows = query.order_by(
        SupplierApplication.created_at.desc(),
        SupplierApplication.id.desc(),
    ).offset((page - 1) * page_size).limit(page_size).all()
    return rows, total


def get_application(
    db: Session,
    application_id: int,
) -> tuple[SupplierApplication, User, list[SupplierApplicationEvent]]:
    row = db.query(SupplierApplication).filter(
        SupplierApplication.id == application_id
    ).first()
    if row is None:
        raise ApiError("SUPPLIER_APPLICATION_NOT_FOUND", "商家申请不存在", 404)
    applicant = db.get(User, row.user_id)
    events = db.query(SupplierApplicationEvent).filter(
        SupplierApplicationEvent.application_id == row.id
    ).order_by(
        SupplierApplicationEvent.created_at.asc(),
        SupplierApplicationEvent.id.asc(),
    ).all()
    return row, applicant, events


def _locked_application(
    db: Session,
    application_id: int,
) -> tuple[SupplierApplication, User]:
    row = db.query(SupplierApplication).filter(
        SupplierApplication.id == application_id
    ).with_for_update().first()
    if row is None:
        raise ApiError("SUPPLIER_APPLICATION_NOT_FOUND", "商家申请不存在", 404)
    applicant = db.query(User).filter(User.id == row.user_id).with_for_update().first()
    if applicant is None:
        raise ApiError("APPLICANT_UNAVAILABLE", "申请账户不存在", 409)
    return row, applicant


def approve_application(
    db: Session,
    admin: User,
    application_id: int,
    *,
    version: int,
    note: str | None,
) -> tuple[SupplierApplication, User, bool]:
    row, applicant = _locked_application(db, application_id)
    if row.status == "approved":
        if applicant.role != "supplier":
            raise ApiError("SUPPLIER_ROLE_CONFLICT", "已通过申请的用户角色不一致", 409)
        return row, applicant, True
    if row.version != version:
        raise ApiError("SUPPLIER_APPLICATION_VERSION_CONFLICT", "申请已被更新，请刷新后重试", 409)
    if row.status != "pending":
        raise ApiError("SUPPLIER_APPLICATION_NOT_REVIEWABLE", "当前申请不能通过审核", 409)
    if applicant.status != "active":
        raise ApiError("APPLICANT_UNAVAILABLE", "申请账户当前不可用", 409)
    if applicant.role not in ("personal", "supplier"):
        raise ApiError("SUPPLIER_ROLE_CONFLICT", "申请账户角色不能升级为商家", 409)
    if not approved_for_user(db, applicant.id):
        raise ApiError(
            "SUPPLIER_KYC_REQUIRED",
            "商家必须先完成实名认证，管理员才能通过入驻申请",
            409,
        )

    previous = row.status
    reviewed_at = _now()
    row.status = "approved"
    row.review_note = note
    row.reviewed_by = admin.id
    row.reviewed_at = reviewed_at
    row.version += 1
    applicant.role = "supplier"
    _add_event(
        db,
        row,
        admin,
        event_type="approved",
        from_status=previous,
        to_status="approved",
        note=note,
        payload={"assigned_role": "supplier"},
    )
    create_notification(
        db,
        user_id=applicant.id,
        category="review",
        title="商家入驻申请已通过",
        body="你的商家身份已经启用，可以开始维护资源与报价。",
        action_path="/supplier",
    )
    _commit(db)
    db.refresh(row)
    db.refresh(applicant)
    return row, applicant, False


def reject_application(
    db: Session,
    admin: User,
    application_id: int,
    *,
    version: int,
    note: str,
) -> tuple[SupplierApplication, User, bool]:
    row, applicant = _locked_application(db, application_id)
    if row.status == "rejected":
        return row, applicant, True
    if row.version != version:
        raise ApiError("SUPPLIER_APPLICATION_VERSION_CONFLICT", "申请已被更新，请刷新后重试", 409)
    if row.status != "pending":
        raise ApiError(
            "SUPPLIER_APPLICATION_NOT_REVIEWABLE",
            "已通过的商家不能通过驳回接口撤销资格",
            409,
        )

    previous = row.status
    row.status = "rejected"
    row.review_note = note
    row.reviewed_by = admin.id
    row.reviewed_at = _now()
    row.version += 1
    removed_role = applicant.role == "supplier"
    if removed_role:
        applicant.role = "personal"
    _add_event(
        db,
        row,
        admin,
        event_type="rejected",
        from_status=previous,
        to_status="rejected",
        note=note,
        payload={"removed_role": "supplier" if removed_role else None},
    )
    create_notification(
        db,
        user_id=applicant.id,
        category="review",
        title="商家入驻申请需要调整",
        body=note,
        action_path="/supplier/apply",
    )
    _commit(db)
    db.refresh(row)
    return row, applicant, False
