from fastapi import APIRouter, Depends, Header, Response, status
from app.models import User
from app.placeholder_schemas import (
    BankAccountBindIn,
    CouponRedeemIn,
    CredentialIssueIn,
    HostedDeviceCreateIn,
    MeteringSyncIn,
    ProvisioningStartIn,
    ReferralInvitationCreateIn,
    WithdrawalCreateIn,
)
from app.responses import ok
from app.security import get_current_user, require_authenticated_action
from app.services import placeholders as placeholder_service


router = APIRouter(
    prefix="/api/v1",
    tags=["placeholder-modules"],
    responses={503: {"description": "模块契约已预留，但真实数据源或服务尚未接入"}},
)


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _empty(response: Response, key: str, field: str):
    _private(response)
    return ok(placeholder_service.empty_collection(key, field), {"real_data_only": True})


def _reject(response: Response, key: str) -> None:
    _private(response)
    placeholder_service.unavailable(key)


@router.get("/account/modules")
def account_modules(response: Response, user: User = Depends(get_current_user)):
    _private(response)
    return ok(placeholder_service.catalog(placeholder_service.ACCOUNT_MODULE_KEYS))


@router.get("/supplier/modules")
def supplier_modules(response: Response, user: User = Depends(get_current_user)):
    _private(response)
    return ok(placeholder_service.catalog(placeholder_service.SUPPLIER_MODULE_KEYS))


@router.get("/supplier/summary")
def supplier_summary(response: Response, user: User = Depends(get_current_user)):
    _private(response)
    return ok({
        "has_data": False,
        "metrics": {
            "published_resources": None,
            "active_orders": None,
            "pending_settlement": None,
            "utilization_rate": None,
        },
        "modules": placeholder_service.catalog(placeholder_service.SUPPLIER_MODULE_KEYS),
    }, {"real_data_only": True})


@router.post("/hosted-devices", status_code=status.HTTP_201_CREATED)
def create_hosted_device(data: HostedDeviceCreateIn, response: Response, idempotency_key: str = Header(min_length=16, max_length=64, alias="Idempotency-Key"), user: User = Depends(require_authenticated_action)):
    _reject(response, "assets")


@router.get("/account/revenue")
def account_revenue(response: Response, user: User = Depends(get_current_user)):
    _private(response)
    return ok(placeholder_service.revenue_snapshot("revenue"), {"real_data_only": True})


@router.post("/account/withdrawals", status_code=status.HTTP_201_CREATED)
def create_account_withdrawal(data: WithdrawalCreateIn, response: Response, idempotency_key: str = Header(min_length=16, max_length=64, alias="Idempotency-Key"), user: User = Depends(require_authenticated_action)):
    _reject(response, "revenue")


@router.get("/account/referrals")
def account_referrals(response: Response, user: User = Depends(get_current_user)):
    _private(response)
    return ok({"referral_code": None, "invitation_url": None, "relations": [], "rewards": [], "module": placeholder_service.descriptor("referrals")}, {"real_data_only": True})


@router.post("/account/referrals/invitations", status_code=status.HTTP_202_ACCEPTED)
def create_referral_invitation(data: ReferralInvitationCreateIn, response: Response, user: User = Depends(require_authenticated_action)):
    _reject(response, "referrals")


@router.get("/account/coupons")
def account_coupons(response: Response, user: User = Depends(get_current_user)):
    return _empty(response, "coupons", "coupons")


@router.post("/account/coupons/redeem")
def redeem_coupon(data: CouponRedeemIn, response: Response, user: User = Depends(require_authenticated_action)):
    _reject(response, "coupons")


@router.get("/account/bank-accounts")
def account_bank_accounts(response: Response, user: User = Depends(get_current_user)):
    return _empty(response, "bank_accounts", "bank_accounts")


@router.post("/account/bank-accounts/bind")
def bind_bank_account(data: BankAccountBindIn, response: Response, user: User = Depends(require_authenticated_action)):
    _reject(response, "bank_accounts")


@router.delete("/account/bank-accounts/{bank_account_id}")
def unbind_bank_account(bank_account_id: int, response: Response, user: User = Depends(require_authenticated_action)):
    _reject(response, "bank_accounts")


@router.get("/supplier/analytics")
def supplier_analytics(response: Response, user: User = Depends(get_current_user)):
    _private(response)
    return ok({"has_data": False, "metrics": {"utilization_rate": None, "order_count": None, "revenue": None}, "series": [], "module": placeholder_service.descriptor("supplier_analytics")}, {"real_data_only": True})


@router.get("/supplier/rebates")
def supplier_rebates(response: Response, user: User = Depends(get_current_user)):
    _private(response)
    return ok({"current_tier": None, "progress": None, "records": [], "module": placeholder_service.descriptor("supplier_rebates")}, {"real_data_only": True})


@router.post("/supplier/resources/{resource_id}/provisioning", status_code=status.HTTP_202_ACCEPTED)
def start_provisioning(resource_id: int, data: ProvisioningStartIn, response: Response, idempotency_key: str = Header(min_length=16, max_length=64, alias="Idempotency-Key"), user: User = Depends(require_authenticated_action)):
    _reject(response, "provisioning")


@router.get("/supplier/resources/{resource_id}/provisioning")
def provisioning_status(resource_id: int, response: Response, user: User = Depends(get_current_user)):
    _private(response)
    return ok({"resource_id": resource_id, "status": "not_configured", "jobs": [], "module": placeholder_service.descriptor("provisioning")}, {"real_data_only": True})


@router.post("/supplier/orders/{order_id}/credentials", status_code=status.HTTP_201_CREATED)
def issue_delivery_credential(order_id: int, data: CredentialIssueIn, response: Response, idempotency_key: str = Header(min_length=16, max_length=64, alias="Idempotency-Key"), user: User = Depends(require_authenticated_action)):
    _reject(response, "credential_vault")


@router.get("/supplier/orders/{order_id}/credential-status")
def delivery_credential_status(order_id: int, response: Response, user: User = Depends(get_current_user)):
    _private(response)
    return ok({"order_id": order_id, "credentials": [], "plaintext_included": False, "module": placeholder_service.descriptor("credential_vault")}, {"real_data_only": True})


@router.post("/supplier/resources/{resource_id}/metering/sync", status_code=status.HTTP_202_ACCEPTED)
def sync_resource_metering(resource_id: int, data: MeteringSyncIn, response: Response, idempotency_key: str = Header(min_length=16, max_length=64, alias="Idempotency-Key"), user: User = Depends(require_authenticated_action)):
    _reject(response, "metering")


@router.get("/supplier/resources/{resource_id}/metering")
def resource_metering(resource_id: int, response: Response, user: User = Depends(get_current_user)):
    _private(response)
    return ok({"resource_id": resource_id, "last_synced_at": None, "periods": [], "module": placeholder_service.descriptor("metering")}, {"real_data_only": True})
