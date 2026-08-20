from math import ceil
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.internal_schemas import (
    AddressCreateIn,
    AddressUpdateIn,
    ApiKeyCreateIn,
    DisputeCreateIn,
    DisputeResolveIn,
    NotificationPreferenceUpdateIn,
    SupplierSettingsUpdateIn,
    TeamCreateIn,
    TeamInvitationCreateIn,
)
from app.models import User
from app.responses import ok
from app.security import get_current_user, require_admin, require_admin_action, require_authenticated_action
from app.services import internal_modules as service


router = APIRouter(prefix="/api/v1", tags=["internal-modules"])
NotificationCategory = Literal["order", "asset", "review", "security", "team", "dispute", "system"]
DisputeStatus = Literal["open", "under_review", "resolved", "rejected", "cancelled"]


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _page_meta(page: int, page_size: int, total: int) -> dict:
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": ceil(total / page_size) if total else 0,
    }


@router.get("/account/addresses")
def list_addresses(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok([service.address_out(row) for row in service.list_addresses(db, user)])


@router.post("/account/addresses", status_code=status.HTTP_201_CREATED)
def create_address(
    data: AddressCreateIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.address_out(service.create_address(db, user, data)))


@router.patch("/account/addresses/{address_id}")
def update_address(
    address_id: int,
    data: AddressUpdateIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.address_out(service.update_address(db, user, address_id, data)))


@router.delete("/account/addresses/{address_id}")
def delete_address(
    address_id: int,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    service.delete_address(db, user, address_id)
    return ok({"deleted": True})


@router.post("/account/addresses/{address_id}/default")
def set_default_address(
    address_id: int,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.address_out(service.set_default_address(db, user, address_id)))


@router.get("/notifications")
def list_notifications(
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    category: NotificationCategory | None = None,
    unread_only: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    rows, total = service.list_notifications(
        db, user, page=page, page_size=page_size, category=category, unread_only=unread_only
    )
    return ok([service.notification_out(row) for row in rows], _page_meta(page, page_size, total))


@router.get("/notifications/unread-count")
def notification_unread_count(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok({"unread_count": service.unread_count(db, user)})


@router.patch("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.notification_out(service.mark_notification_read(db, user, notification_id)))


@router.post("/notifications/read-all")
def mark_all_notifications_read(
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok({"updated_count": service.mark_all_notifications_read(db, user)})


def _notification_preferences_response(row) -> dict:
    return {
        "preferences": service.notification_preference_out(row),
        "delivery": {
            "in_app_enabled": True,
            "system_push_configured": False,
            "system_push_provider": None,
            "system_push_status": "pending_configuration",
        },
    }


@router.get("/notifications/preferences")
def get_notification_preferences(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(_notification_preferences_response(service.get_notification_preference(db, user)))


@router.put("/notifications/preferences")
def update_notification_preferences(
    data: NotificationPreferenceUpdateIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    row = service.save_notification_preference(db, user, data)
    return ok(_notification_preferences_response(row))


@router.get("/supplier/settings")
def get_supplier_settings(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    profile, application = service.get_supplier_profile(db, user)
    return ok({
        "profile": service.supplier_profile_out(profile),
        "application": {
            "company_name": application.company_name,
            "contact_name": application.contact_name,
            "contact_phone": application.contact_phone,
            "region": application.region,
        },
    })


@router.put("/supplier/settings")
def update_supplier_settings(
    data: SupplierSettingsUpdateIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.supplier_profile_out(service.save_supplier_profile(db, user, data)))


@router.get("/account/disputes")
def list_account_disputes(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok([service.dispute_out(row) for row in service.list_disputes(db, user)])


@router.post("/account/disputes", status_code=status.HTTP_201_CREATED)
def create_account_dispute(
    data: DisputeCreateIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.dispute_out(service.create_dispute(db, user, data)))


@router.get("/account/disputes/{dispute_id}")
def get_account_dispute(
    dispute_id: int,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    row, events = service.dispute_detail(db, user, dispute_id)
    return ok({
        "dispute": service.dispute_out(row),
        "events": [service.dispute_event_out(event) for event in events],
    })


@router.get("/admin/disputes")
def list_admin_disputes(
    response: Response,
    dispute_status: Annotated[DisputeStatus | None, Query(alias="status")] = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok([service.dispute_out(row) for row in service.admin_list_disputes(db, dispute_status)])


@router.patch("/admin/disputes/{dispute_id}")
def resolve_admin_dispute(
    dispute_id: int,
    data: DisputeResolveIn,
    response: Response,
    admin: User = Depends(require_admin_action),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.dispute_out(service.resolve_dispute(db, admin, dispute_id, data)))


@router.get("/account/teams")
def list_teams(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.list_teams(db, user))


@router.post("/account/teams", status_code=status.HTTP_201_CREATED)
def create_team(
    data: TeamCreateIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    row = service.create_team(db, user, data)
    return ok(service.team_out(db, row))


@router.post("/account/teams/{team_id}/invitations", status_code=status.HTTP_201_CREATED)
def invite_team_member(
    team_id: int,
    data: TeamInvitationCreateIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    row = service.invite_team_member(db, user, team_id, data)
    return ok({
        "id": row.id,
        "team_id": row.team_id,
        "email": row.email,
        "role": row.role,
        "status": row.status,
        "expires_at": row.expires_at,
    })


@router.post("/account/teams/invitations/{invitation_id}/accept")
def accept_team_invitation(
    invitation_id: int,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    service.accept_team_invitation(db, user, invitation_id)
    return ok({"accepted": True})


@router.get("/account/api-keys")
def list_api_keys(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok([service.api_key_out(row) for row in service.list_api_keys(db, user)])


@router.post("/account/api-keys", status_code=status.HTTP_201_CREATED)
def create_api_key(
    data: ApiKeyCreateIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    row, raw_key = service.create_api_key(db, user, data)
    return ok({**service.api_key_out(row), "secret": raw_key, "shown_once": True})


@router.delete("/account/api-keys/{api_key_id}")
def revoke_api_key(
    api_key_id: int,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.api_key_out(service.revoke_api_key(db, user, api_key_id)))
