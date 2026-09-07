"""Public and authenticated account-recovery HTTP boundaries."""

from fastapi import APIRouter, Depends, Response
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import (
    limit_password_reset_request,
    limit_recovery_confirm,
    limit_recovery_email_binding,
)
from app.db.session import get_db
from app.integrations.account_email import email_delivery_configured
from app.models.user import User
from app.core.deps import AuthContext, get_current_auth_context, get_current_user
from app.schemas.auth import (
    PasswordResetConfirmIn,
    PasswordResetRequestIn,
    RecoveryEmailVerificationRequestIn,
    RecoveryTokenIn,
)
from app.services import account_recovery as recovery
from app.services import kai_auth
from app.utils.response import BizError, error, success


class RecoveryRoute(APIRoute):
    """Prevent submitted credentials/tokens from appearing in 422 responses."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request):
            try:
                result = await handler(request)
            except RequestValidationError:
                result = JSONResponse(
                    status_code=422,
                    content=error("找回请求参数无效，请检查后重试"),
                )
            except BizError as exc:
                result = JSONResponse(
                    status_code=exc.status_code,
                    content=error(exc.msg, exc.code),
                )
            except HTTPException as exc:
                message = exc.detail if isinstance(exc.detail, str) else "请求错误"
                result = JSONResponse(
                    status_code=exc.status_code,
                    content=error(message),
                    headers=exc.headers,
                )
            result.headers["Cache-Control"] = "no-store"
            result.headers["Referrer-Policy"] = "no-referrer"
            return result

        return handle


def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


router = APIRouter(
    tags=["account-recovery"],
    route_class=RecoveryRoute,
    dependencies=[Depends(no_store)],
)
_GENERIC_REQUEST_RESULT = {
    "accepted": True,
    "message": "如果该邮箱已绑定，重置邮件会在几分钟内送达",
}


@router.get("/api/auth/recovery/config")
def recovery_config():
    return success({
        "email_enabled": email_delivery_configured(),
        "kai_enabled": kai_auth.is_configured(),
        "reset_ttl_seconds": settings.ACCOUNT_RECOVERY_RESET_TTL_SECONDS,
    })


@router.post("/api/user/recovery-email/request-verification")
def request_recovery_email_verification(
    data: RecoveryEmailVerificationRequestIn,
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
):
    user = context.user
    limit_recovery_email_binding(user.id)
    already_verified, _token, _recipient = recovery.request_email_verification(
        db,
        user,
        data.email,
        data.current_password,
        context.session_id,
    )
    return success({"accepted": True, "already_verified": already_verified})


@router.get("/api/user/recovery-email")
def get_recovery_email(user: User = Depends(get_current_user)):
    return success(recovery.recovery_email_status(user))


@router.post("/api/auth/email/verification/confirm")
def confirm_recovery_email(data: RecoveryTokenIn, db: Session = Depends(get_db)):
    limit_recovery_confirm(data.token)
    recovery.confirm_recovery_email(db, data.token)
    return success({"verified": True})


@router.post("/api/auth/email/password-reset/request")
def request_password_reset(
    data: PasswordResetRequestIn,
    db: Session = Depends(get_db),
):
    limit_password_reset_request(data.email)
    recovery.request_password_reset(db, data.email)
    return success(_GENERIC_REQUEST_RESULT)


@router.post("/api/auth/email/password-reset/confirm")
def confirm_password_reset(
    data: PasswordResetConfirmIn,
    db: Session = Depends(get_db),
):
    limit_recovery_confirm(data.token)
    recovery.reset_password(db, data.token, data.password)
    return success({"reset": True})
