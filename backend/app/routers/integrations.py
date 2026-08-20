from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.integration_schemas import KycStartIn, PaymentIntentCreateIn, UploadCompleteIn, UploadInitIn
from app.kyc_schemas import ManualKycSubmitIn
from app.models import User
from app.responses import ok
from app.security import get_current_user, require_csrf
from app.services import integrations as integration_service
from app.services import manual_kyc


router = APIRouter(prefix="/api/v1", tags=["integrations"])


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/account/integrations")
def account_integrations(
    response: Response,
    user: User = Depends(get_current_user),
):
    _private(response)
    return ok(integration_service.provider_status())


@router.get("/account/wallet")
def account_wallet(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(integration_service.wallet_snapshot(db, user), {"real_data_only": True})


@router.post("/payments/intents", status_code=status.HTTP_201_CREATED)
def create_payment_intent(
    data: PaymentIntentCreateIn,
    request: Request,
    response: Response,
    idempotency_key: str = Header(min_length=16, max_length=64, alias="Idempotency-Key"),
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    row = integration_service.create_payment_intent(
        db,
        user,
        data,
        idempotency_key=idempotency_key,
        client_ip=request.client.host if request.client else "127.0.0.1",
    )
    return ok(integration_service.payment_intent_out(row))


@router.get("/payments/{payment_no}/credential")
def payment_credential(
    payment_no: str,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(integration_service.payment_checkout_payload(db, user, payment_no))


@router.post("/payments/{payment_no}/reconcile")
def reconcile_payment(
    payment_no: str,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(integration_service.reconcile_pingxx_payment(db, user, payment_no))


@router.post(
    "/payments/webhooks/pingxx",
    response_class=PlainTextResponse,
    operation_id="pingxx_payment_webhook",
)
async def pingxx_webhook(
    request: Request,
    signature: str = Header(default="", alias="x-pingplusplus-signature", max_length=1024),
    db: Session = Depends(get_db),
):
    raw_body = await request.body()
    if len(raw_body) > 64 * 1024:
        return PlainTextResponse("payload too large", status_code=413)
    integration_service.process_pingxx_webhook(db, raw_body, signature)
    return PlainTextResponse("success", headers={"Cache-Control": "no-store"})


@router.get("/account/kyc")
def account_kyc(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(manual_kyc.snapshot(db, user), {"sensitive_data_included": False})


@router.post("/account/kyc/manual", status_code=status.HTTP_201_CREATED)
def submit_manual_kyc(
    data: ManualKycSubmitIn,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    row = manual_kyc.submit(db, user, data)
    return ok(manual_kyc.application_out(row))


@router.post("/account/kyc/start")
def start_kyc(
    data: KycStartIn,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    row, verification_url = integration_service.start_kyc(db, user, data)
    return ok({
        "application_id": row.id,
        "status": row.status,
        "verification_url": verification_url,
    })


@router.get("/account/files")
def account_files(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(integration_service.file_snapshot(db, user), {"private_metadata_only": True})


@router.post("/files/upload/init", status_code=status.HTTP_201_CREATED)
def init_private_upload(
    data: UploadInitIn,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    row, upload, target = integration_service.init_upload(db, user, data)
    return ok({
        "file": integration_service.stored_object_out(row),
        "upload_id": upload.id,
        "upload_url": target.upload_url,
        "method": target.method,
        "headers": target.headers,
        "expires_at": upload.expires_at,
    })


@router.post("/files/upload/complete")
def complete_private_upload(
    data: UploadCompleteIn,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    row = integration_service.complete_upload(db, user, data.upload_id, data.etag)
    return ok(integration_service.stored_object_out(row))
