import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.internal_schemas import (
    AddressCreateIn,
    AddressUpdateIn,
    ApiKeyCreateIn,
    DisputeCreateIn,
    DisputeResolveIn,
    SupplierSettingsUpdateIn,
    TeamCreateIn,
    TeamInvitationCreateIn,
)
from app.models import (
    AccessLease,
    ApiCredential,
    DisputeCase,
    DisputeEvent,
    EmailOutbox,
    Notification,
    Order,
    PaymentIntent,
    StoredObject,
    SupplierApplication,
    SupplierProfile,
    Team,
    TeamInvitation,
    TeamMember,
    User,
    UserAddress,
)
from app.config import settings
from app.security import ApiError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _commit(db: Session, code: str = "DATA_CONFLICT") -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(code, "数据发生冲突，请刷新后重试", 409) from exc


def create_notification(
    db: Session,
    *,
    user_id: int,
    category: str,
    title: str,
    body: str,
    action_path: str | None = None,
) -> Notification:
    row = Notification(
        user_id=user_id,
        category=category,
        title=title,
        body=body,
        action_path=action_path,
    )
    db.add(row)
    if settings.EMAIL_NOTIFICATION_ENABLED and category in {"review", "order", "payment", "settlement", "dispute"}:
        recipient = db.get(User, user_id)
        if recipient and recipient.email and recipient.email_verified:
            action_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}{action_path}" if action_path else None
            db.add(EmailOutbox(
                user_id=user_id,
                destination=recipient.email,
                subject=title,
                text_body=body,
                action_url=action_url,
            ))
    return row


def notification_out(row: Notification) -> dict:
    return {
        "id": row.id,
        "category": row.category,
        "title": row.title,
        "body": row.body,
        "action_path": row.action_path,
        "is_read": row.is_read,
        "read_at": row.read_at,
        "created_at": row.created_at,
    }


def list_notifications(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    category: str | None,
    unread_only: bool,
) -> tuple[list[Notification], int]:
    query = db.query(Notification).filter(Notification.user_id == user.id)
    if category:
        query = query.filter(Notification.category == category)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    total = query.count()
    rows = query.order_by(Notification.created_at.desc(), Notification.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return rows, total


def unread_count(db: Session, user: User) -> int:
    return db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.is_read.is_(False),
    ).count()


def mark_notification_read(db: Session, user: User, notification_id: int) -> Notification:
    row = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == user.id,
    ).first()
    if row is None:
        raise ApiError("NOTIFICATION_NOT_FOUND", "通知不存在", 404)
    if not row.is_read:
        row.is_read = True
        row.read_at = _now()
        db.commit()
        db.refresh(row)
    return row


def mark_all_notifications_read(db: Session, user: User) -> int:
    now = _now()
    count = db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.is_read.is_(False),
    ).update({Notification.is_read: True, Notification.read_at: now}, synchronize_session=False)
    db.commit()
    return count


def address_out(row: UserAddress) -> dict:
    return {
        "id": row.id,
        "label": row.label,
        "recipient_name": row.recipient_name,
        "phone": row.phone,
        "country_code": row.country_code,
        "province": row.province,
        "city": row.city,
        "district": row.district,
        "address_line": row.address_line,
        "postal_code": row.postal_code,
        "is_default": row.is_default,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "version": row.version,
    }


def list_addresses(db: Session, user: User) -> list[UserAddress]:
    return db.query(UserAddress).filter(UserAddress.user_id == user.id).order_by(
        UserAddress.is_default.desc(), UserAddress.created_at.desc(), UserAddress.id.desc()
    ).all()


def _owned_address(db: Session, user: User, address_id: int, *, lock: bool = False) -> UserAddress:
    query = db.query(UserAddress).filter(
        UserAddress.id == address_id,
        UserAddress.user_id == user.id,
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise ApiError("ADDRESS_NOT_FOUND", "地址不存在", 404)
    return row


def _clear_default_address(db: Session, user_id: int, *, except_id: int | None = None) -> None:
    query = db.query(UserAddress).filter(
        UserAddress.user_id == user_id,
        UserAddress.is_default.is_(True),
    )
    if except_id is not None:
        query = query.filter(UserAddress.id != except_id)
    query.update({UserAddress.is_default: False}, synchronize_session=False)


def create_address(db: Session, user: User, data: AddressCreateIn) -> UserAddress:
    has_address = db.query(UserAddress.id).filter(UserAddress.user_id == user.id).first() is not None
    make_default = data.is_default or not has_address
    if make_default:
        _clear_default_address(db, user.id)
    row = UserAddress(
        user_id=user.id,
        **data.model_dump(exclude={"is_default"}),
        is_default=make_default,
    )
    db.add(row)
    _commit(db, "ADDRESS_CONFLICT")
    db.refresh(row)
    return row


def update_address(db: Session, user: User, address_id: int, data: AddressUpdateIn) -> UserAddress:
    row = _owned_address(db, user, address_id, lock=True)
    if row.version != data.version:
        raise ApiError("ADDRESS_VERSION_CONFLICT", "地址已被更新，请刷新后重试", 409)
    values = data.model_dump(exclude_unset=True)
    values.pop("version", None)
    make_default = values.pop("is_default", None)
    if make_default is True:
        _clear_default_address(db, user.id, except_id=row.id)
        row.is_default = True
    elif make_default is False and row.is_default:
        raise ApiError("DEFAULT_ADDRESS_REQUIRED", "请先将另一个地址设为默认地址", 409)
    for key, value in values.items():
        setattr(row, key, value)
    row.version += 1
    _commit(db, "ADDRESS_CONFLICT")
    db.refresh(row)
    return row


def delete_address(db: Session, user: User, address_id: int) -> None:
    row = _owned_address(db, user, address_id, lock=True)
    was_default = row.is_default
    db.delete(row)
    db.flush()
    if was_default:
        replacement = db.query(UserAddress).filter(UserAddress.user_id == user.id).order_by(
            UserAddress.created_at.desc(), UserAddress.id.desc()
        ).first()
        if replacement:
            replacement.is_default = True
            replacement.version += 1
    _commit(db, "ADDRESS_CONFLICT")


def set_default_address(db: Session, user: User, address_id: int) -> UserAddress:
    row = _owned_address(db, user, address_id, lock=True)
    if not row.is_default:
        _clear_default_address(db, user.id, except_id=row.id)
        row.is_default = True
        row.version += 1
        _commit(db, "ADDRESS_CONFLICT")
        db.refresh(row)
    return row


def _require_approved_supplier(db: Session, user: User) -> SupplierApplication:
    row = db.query(SupplierApplication).filter(
        SupplierApplication.user_id == user.id,
        SupplierApplication.status == "approved",
    ).first()
    if user.role != "supplier" or row is None:
        raise ApiError("SUPPLIER_APPROVAL_REQUIRED", "商家审核通过后才能使用商家设置", 403)
    return row


def supplier_profile_out(row: SupplierProfile | None) -> dict | None:
    if row is None:
        return None
    return {
        "store_name": row.store_name,
        "contact_name": row.contact_name,
        "contact_phone": row.contact_phone,
        "service_regions": row.service_regions,
        "introduction": row.introduction,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "version": row.version,
    }


def get_supplier_profile(db: Session, user: User) -> tuple[SupplierProfile | None, SupplierApplication]:
    application = _require_approved_supplier(db, user)
    return db.get(SupplierProfile, user.id), application


def save_supplier_profile(db: Session, user: User, data: SupplierSettingsUpdateIn) -> SupplierProfile:
    application = _require_approved_supplier(db, user)
    row = db.get(SupplierProfile, user.id)
    if row is None:
        row = SupplierProfile(
            user_id=user.id,
            store_name=data.store_name or application.company_name,
            contact_name=data.contact_name,
            contact_phone=data.contact_phone,
            service_regions=data.service_regions,
            introduction=data.introduction,
        )
        db.add(row)
    else:
        if data.version is None or data.version != row.version:
            raise ApiError("SUPPLIER_PROFILE_VERSION_CONFLICT", "商家资料已更新，请刷新后重试", 409)
        row.store_name = data.store_name
        row.contact_name = data.contact_name
        row.contact_phone = data.contact_phone
        row.service_regions = data.service_regions
        row.introduction = data.introduction
        row.version += 1
    _commit(db, "SUPPLIER_PROFILE_CONFLICT")
    db.refresh(row)
    return row


def _dispute_number() -> str:
    return f"DP{_now():%Y%m%d}{uuid4().hex[:12].upper()}"


def dispute_out(row: DisputeCase) -> dict:
    return {
        "id": row.id,
        "dispute_no": row.dispute_no,
        "order_id": row.order_id,
        "opened_by_user_id": row.opened_by_user_id,
        "counterparty_user_id": row.counterparty_user_id,
        "status": row.status,
        "reason": row.reason,
        "description": row.description,
        "attachment_object_ids": row.attachment_object_ids,
        "resolution": row.resolution,
        "resolution_action": row.resolution_action,
        "resolved_at": row.resolved_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "version": row.version,
    }


def dispute_event_out(row: DisputeEvent) -> dict:
    return {
        "id": row.id,
        "actor_user_id": row.actor_user_id,
        "event_type": row.event_type,
        "payload": row.payload,
        "created_at": row.created_at,
    }


def list_disputes(db: Session, user: User) -> list[DisputeCase]:
    return db.query(DisputeCase).filter(or_(
        DisputeCase.opened_by_user_id == user.id,
        DisputeCase.counterparty_user_id == user.id,
    )).order_by(DisputeCase.updated_at.desc(), DisputeCase.id.desc()).all()


def _visible_dispute(db: Session, user: User, dispute_id: int) -> DisputeCase:
    row = db.query(DisputeCase).filter(
        DisputeCase.id == dispute_id,
        or_(DisputeCase.opened_by_user_id == user.id, DisputeCase.counterparty_user_id == user.id),
    ).first()
    if row is None:
        raise ApiError("DISPUTE_NOT_FOUND", "争议工单不存在", 404)
    return row


def create_dispute(db: Session, user: User, data: DisputeCreateIn) -> DisputeCase:
    order = db.query(Order).filter(
        Order.id == data.order_id,
        or_(Order.buyer_id == user.id, Order.supplier_id == user.id),
    ).with_for_update().first()
    if order is None:
        raise ApiError("ORDER_NOT_FOUND", "订单不存在", 404)
    if order.status not in ("confirmed", "delivering", "delivered", "completed"):
        raise ApiError("ORDER_NOT_DISPUTABLE", "当前订单状态不能发起争议", 409)
    lease = db.query(AccessLease).filter(AccessLease.order_id == order.id).first()
    if lease is not None:
        if lease.expires_at is not None:
            dispute_deadline = _aware(lease.expires_at) + timedelta(
                hours=settings.SETTLEMENT_HOLD_HOURS
            )
            if _now() > dispute_deadline:
                raise ApiError(
                    "DISPUTE_WINDOW_CLOSED",
                    "服务器租约的争议期已经结束，商家款项已进入结算",
                    409,
                )
        intents = db.query(PaymentIntent).filter(
            PaymentIntent.order_id == order.id,
            PaymentIntent.purpose.in_(("server_rental", "lease_renewal")),
        ).all()
        if any(
            (intent.metadata_payload or {}).get("funds_state")
            in {"released", "refund_pending", "refunded"}
            for intent in intents
        ):
            raise ApiError(
                "DISPUTE_FUNDS_UNAVAILABLE",
                "订单资金已经结算或进入退款，不能重复发起争议",
                409,
            )
    existing = db.query(DisputeCase.id).filter(
        DisputeCase.order_id == order.id,
        DisputeCase.opened_by_user_id == user.id,
        DisputeCase.status.in_(("open", "under_review")),
    ).first()
    if existing:
        raise ApiError("ACTIVE_DISPUTE_EXISTS", "该订单已有处理中的争议", 409)
    if data.attachment_object_ids:
        owned_count = db.query(StoredObject).filter(
            StoredObject.id.in_(data.attachment_object_ids),
            StoredObject.owner_user_id == user.id,
            StoredObject.status == "available",
        ).count()
        if owned_count != len(set(data.attachment_object_ids)):
            raise ApiError("DISPUTE_ATTACHMENT_INVALID", "争议附件不存在或不可用", 422)
    counterparty_id = order.supplier_id if order.buyer_id == user.id else order.buyer_id
    row = DisputeCase(
        dispute_no=_dispute_number(),
        order_id=order.id,
        opened_by_user_id=user.id,
        counterparty_user_id=counterparty_id,
        reason=data.reason,
        description=data.description,
        attachment_object_ids=data.attachment_object_ids,
    )
    db.add(row)
    db.flush()
    db.add(DisputeEvent(
        dispute_id=row.id,
        actor_user_id=user.id,
        event_type="opened",
        payload={"reason": data.reason},
    ))
    create_notification(
        db,
        user_id=counterparty_id,
        category="dispute",
        title="订单出现新的争议工单",
        body=f"订单 {order.order_no} 已发起争议，请及时查看。",
        action_path="/account/disputes",
    )
    _commit(db, "DISPUTE_CONFLICT")
    db.refresh(row)
    return row


def dispute_detail(db: Session, user: User, dispute_id: int) -> tuple[DisputeCase, list[DisputeEvent]]:
    row = _visible_dispute(db, user, dispute_id)
    events = db.query(DisputeEvent).filter(DisputeEvent.dispute_id == row.id).order_by(
        DisputeEvent.created_at.asc(), DisputeEvent.id.asc()
    ).all()
    return row, events


def admin_list_disputes(db: Session, status: str | None) -> list[DisputeCase]:
    query = db.query(DisputeCase)
    if status:
        query = query.filter(DisputeCase.status == status)
    return query.order_by(DisputeCase.updated_at.desc(), DisputeCase.id.desc()).all()


def resolve_dispute(db: Session, admin: User, dispute_id: int, data: DisputeResolveIn) -> DisputeCase:
    row = db.query(DisputeCase).filter(DisputeCase.id == dispute_id).with_for_update().first()
    if row is None:
        raise ApiError("DISPUTE_NOT_FOUND", "争议工单不存在", 404)
    if row.version != data.version:
        raise ApiError("DISPUTE_VERSION_CONFLICT", "争议工单已更新，请刷新后重试", 409)
    if row.status in ("resolved", "rejected", "cancelled"):
        raise ApiError("DISPUTE_ALREADY_CLOSED", "争议工单已经关闭", 409)
    if data.status in ("resolved", "rejected") and not data.resolution:
        raise ApiError("DISPUTE_RESOLUTION_REQUIRED", "关闭争议时必须填写处理结论", 422)
    row.status = data.status
    row.resolution = data.resolution
    row.resolution_action = data.resolution_action
    row.version += 1
    finance_result: dict = {}
    if data.status in ("resolved", "rejected"):
        row.resolved_at = _now()
        row.resolved_by_user_id = admin.id
        from app.services.server_rentals import release_frozen_payment, request_dispute_refunds

        if data.resolution_action == "refund_buyer":
            refunds = request_dispute_refunds(
                db,
                row,
                resolution=data.resolution or "管理员裁决买家胜诉",
            )
            finance_result["refund_nos"] = [refund.refund_no for refund in refunds]
        elif data.resolution_action == "release_to_supplier":
            intents = db.query(PaymentIntent).filter(
                PaymentIntent.order_id == row.order_id,
                PaymentIntent.purpose.in_(("server_rental", "lease_renewal")),
                PaymentIntent.status == "succeeded",
            ).with_for_update().all()
            finance_result["payments_released"] = sum(
                1 for intent in intents if release_frozen_payment(db, intent)
            )
    db.add(DisputeEvent(
        dispute_id=row.id,
        actor_user_id=admin.id,
        event_type=data.status,
        payload={
            "resolution": data.resolution,
            "resolution_action": data.resolution_action,
            **finance_result,
        },
    ))
    for target in {row.opened_by_user_id, row.counterparty_user_id}:
        create_notification(
            db,
            user_id=target,
            category="dispute",
            title="争议工单状态已更新",
            body=(
                f"工单 {row.dispute_no} 已裁决并进入退款处理。"
                if data.resolution_action == "refund_buyer"
                else f"工单 {row.dispute_no} 已驳回，订单将按规则继续结算。"
                if data.resolution_action == "release_to_supplier"
                else f"工单 {row.dispute_no} 已更新为 {data.status}。"
            ),
            action_path="/account/disputes",
        )
    _commit(db, "DISPUTE_CONFLICT")
    db.refresh(row)
    return row


def team_out(db: Session, row: Team) -> dict:
    members = db.query(TeamMember, User).join(User, User.id == TeamMember.user_id).filter(
        TeamMember.team_id == row.id,
        TeamMember.status == "active",
    ).order_by(TeamMember.joined_at.asc()).all()
    return {
        "id": row.id,
        "name": row.name,
        "owner_user_id": row.owner_user_id,
        "members": [{
            "user_id": member.user_id,
            "display_name": member_user.display_name,
            "email": member_user.email,
            "role": member.role,
            "joined_at": member.joined_at,
        } for member, member_user in members],
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "version": row.version,
    }


def list_teams(db: Session, user: User) -> dict:
    rows = db.query(Team).join(TeamMember, TeamMember.team_id == Team.id).filter(
        TeamMember.user_id == user.id,
        TeamMember.status == "active",
    ).order_by(Team.updated_at.desc(), Team.id.desc()).all()
    invitations = []
    if user.email:
        invitations = db.query(TeamInvitation, Team).join(Team, Team.id == TeamInvitation.team_id).filter(
            func.lower(TeamInvitation.email) == user.email.lower(),
            TeamInvitation.status == "pending",
        ).order_by(TeamInvitation.created_at.desc()).all()
    return {
        "teams": [team_out(db, row) for row in rows],
        "received_invitations": [{
            "id": invitation.id,
            "team_id": team.id,
            "team_name": team.name,
            "role": invitation.role,
            "expires_at": invitation.expires_at,
        } for invitation, team in invitations if _aware(invitation.expires_at) > _now()],
    }


def create_team(db: Session, user: User, data: TeamCreateIn) -> Team:
    row = Team(owner_user_id=user.id, name=data.name.strip())
    db.add(row)
    db.flush()
    db.add(TeamMember(team_id=row.id, user_id=user.id, role="owner", status="active"))
    _commit(db, "TEAM_CONFLICT")
    db.refresh(row)
    return row


def _manageable_team(db: Session, user: User, team_id: int) -> Team:
    row = db.query(Team).join(TeamMember, TeamMember.team_id == Team.id).filter(
        Team.id == team_id,
        TeamMember.user_id == user.id,
        TeamMember.status == "active",
        TeamMember.role.in_(("owner", "admin")),
    ).first()
    if row is None:
        raise ApiError("TEAM_MANAGE_FORBIDDEN", "没有权限管理该团队", 403)
    return row


def invite_team_member(
    db: Session, user: User, team_id: int, data: TeamInvitationCreateIn
) -> TeamInvitation:
    team = _manageable_team(db, user, team_id)
    email = str(data.email).lower()
    target = db.query(User).filter(func.lower(User.email) == email).first()
    if target and db.query(TeamMember.id).filter(
        TeamMember.team_id == team.id,
        TeamMember.user_id == target.id,
        TeamMember.status == "active",
    ).first():
        raise ApiError("TEAM_MEMBER_EXISTS", "该用户已经是团队成员", 409)
    row = db.query(TeamInvitation).filter(
        TeamInvitation.team_id == team.id,
        TeamInvitation.email == email,
    ).first()
    expires_at = _now() + timedelta(days=7)
    if row is None:
        row = TeamInvitation(
            team_id=team.id,
            invited_by_user_id=user.id,
            email=email,
            role=data.role,
            expires_at=expires_at,
        )
        db.add(row)
    else:
        row.invited_by_user_id = user.id
        row.role = data.role
        row.status = "pending"
        row.expires_at = expires_at
        row.accepted_at = None
    if target:
        create_notification(
            db,
            user_id=target.id,
            category="team",
            title="你收到一份团队邀请",
            body=f"{user.display_name} 邀请你加入团队“{team.name}”。",
            action_path="/account/teams",
        )
    _commit(db, "TEAM_INVITATION_CONFLICT")
    db.refresh(row)
    return row


def accept_team_invitation(db: Session, user: User, invitation_id: int) -> Team:
    if not user.email:
        raise ApiError("VERIFIED_EMAIL_REQUIRED", "绑定邮箱后才能接受团队邀请", 409)
    invitation = db.query(TeamInvitation).filter(
        TeamInvitation.id == invitation_id,
        func.lower(TeamInvitation.email) == user.email.lower(),
    ).with_for_update().first()
    if invitation is None:
        raise ApiError("TEAM_INVITATION_NOT_FOUND", "团队邀请不存在", 404)
    if invitation.status != "pending" or _aware(invitation.expires_at) <= _now():
        raise ApiError("TEAM_INVITATION_EXPIRED", "团队邀请已失效", 409)
    member = db.query(TeamMember).filter(
        TeamMember.team_id == invitation.team_id,
        TeamMember.user_id == user.id,
    ).first()
    if member is None:
        db.add(TeamMember(
            team_id=invitation.team_id,
            user_id=user.id,
            role=invitation.role,
            status="active",
        ))
    else:
        member.role = invitation.role
        member.status = "active"
    invitation.status = "accepted"
    invitation.accepted_at = _now()
    team = db.get(Team, invitation.team_id)
    create_notification(
        db,
        user_id=team.owner_user_id,
        category="team",
        title="团队邀请已接受",
        body=f"{user.display_name} 已加入团队“{team.name}”。",
        action_path="/account/teams",
    )
    _commit(db, "TEAM_INVITATION_CONFLICT")
    db.refresh(team)
    return team


def api_key_out(row: ApiCredential) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "key_prefix": row.key_prefix,
        "scopes": row.scopes,
        "status": row.status,
        "expires_at": row.expires_at,
        "last_used_at": row.last_used_at,
        "revoked_at": row.revoked_at,
        "created_at": row.created_at,
    }


def list_api_keys(db: Session, user: User) -> list[ApiCredential]:
    return db.query(ApiCredential).filter(ApiCredential.user_id == user.id).order_by(
        ApiCredential.created_at.desc(), ApiCredential.id.desc()
    ).all()


def create_api_key(db: Session, user: User, data: ApiKeyCreateIn) -> tuple[ApiCredential, str]:
    raw = f"wod_live_{secrets.token_urlsafe(32)}"
    row = ApiCredential(
        user_id=user.id,
        name=data.name.strip(),
        key_prefix=raw[:16],
        secret_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        scopes=list(dict.fromkeys(data.scopes)),
        expires_at=_now() + timedelta(days=data.expires_in_days) if data.expires_in_days else None,
    )
    db.add(row)
    _commit(db, "API_KEY_CONFLICT")
    db.refresh(row)
    return row, raw


def revoke_api_key(db: Session, user: User, api_key_id: int) -> ApiCredential:
    row = db.query(ApiCredential).filter(
        ApiCredential.id == api_key_id,
        ApiCredential.user_id == user.id,
    ).first()
    if row is None:
        raise ApiError("API_KEY_NOT_FOUND", "API Key 不存在", 404)
    if row.status != "revoked":
        row.status = "revoked"
        row.revoked_at = _now()
        db.commit()
        db.refresh(row)
    return row
