import hashlib

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rate_limit import SlidingWindowRateLimiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.account_deletion import (
    DeletionPasswordIn, DeletionResponse, DeletionSubmitIn, DeletionTicketIn,
    EligibilityResponse, TicketResponse,
)
from app.services import account_deletion as deletion
from app.utils.response import BizError, error, success


class DeletionRoute(APIRoute):
    """Keep deletion secrets out of validation errors and cached responses."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request: Request):
            try:
                response = await handler(request)
            except RequestValidationError:
                # FastAPI's default 422 includes the submitted input, which may
                # contain a password or deletion capability. Never echo it.
                response = JSONResponse(status_code=422, content=error("注销请求参数无效，请检查后重试"))
            except BizError as exc:
                response = JSONResponse(status_code=exc.status_code, content=error(exc.msg, exc.code))
            except HTTPException as exc:
                message = exc.detail if isinstance(exc.detail, str) else "请求错误"
                response = JSONResponse(status_code=exc.status_code, content=error(message), headers=exc.headers)
            response.headers["Cache-Control"] = "no-store"
            return response

        return handle


def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/user/account-deletion", tags=["account-deletion"], route_class=DeletionRoute, dependencies=[Depends(no_store)])
_password_limit = SlidingWindowRateLimiter(limit=5, window_seconds=300)
_ticket_limit = SlidingWindowRateLimiter(limit=30, window_seconds=60)
_invalid_peer_limit = SlidingWindowRateLimiter(limit=60, window_seconds=60)
_INVALID_PEER_BUCKETS = 256


def _invalid_peer_key(request: Request) -> str:
    # Only use the ASGI connection peer, never caller-controlled Forwarded or
    # X-Forwarded-For headers. Fixed slots bound memory even for distributed
    # random-ticket traffic. Collisions affect invalid requests only: a real
    # receipt always has its own independent server-issued ticket bucket.
    peer = request.client.host if request.client else "unknown-peer"
    slot = int.from_bytes(hashlib.sha256(peer.encode()).digest()[:2], "big") % _INVALID_PEER_BUCKETS
    return f"deletion:invalid-peer:{slot}"


def _limit_public_request(ticket: str, request: Request, db: Session) -> None:
    # An attacker cannot allocate a limiter key by inventing a ticket: first
    # require a persisted, unexpired deletion receipt. This indexed lookup is
    # read-only; submit/status still perform their own lifecycle validation.
    try:
        row = deletion._request(db, ticket)
    except BizError:
        _invalid_peer_limit.check(_invalid_peer_key(request))
        raise
    _ticket_limit.check(f"deletion:ticket:{row.ticket_hash}")


@router.get("/eligibility", response_model=EligibilityResponse)
def eligibility(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return success(deletion.eligibility(db, user))


@router.post("/verify", response_model=TicketResponse)
def verify(data: DeletionPasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _password_limit.check(f"deletion:{user.id}")
    return success(deletion.verify_deletion_password(db, user, data.password))


@router.post("/submit", response_model=DeletionResponse)
def submit(data: DeletionSubmitIn, tasks: BackgroundTasks, request: Request, db: Session = Depends(get_db)):
    # No normal bearer token is needed here: this capability already carries
    # fresh verification and can be retried after the account session is revoked.
    _limit_public_request(data.ticket, request, db)
    result = deletion.submit_deletion(db, data.ticket, data.confirm)
    if result["status"] == "processing":
        tasks.add_task(deletion.process_ticket, data.ticket)
    return success(result)


@router.post("/status", response_model=DeletionResponse)
def status(data: DeletionTicketIn, request: Request, db: Session = Depends(get_db)):
    _limit_public_request(data.ticket, request, db)
    return success(deletion.deletion_status(db, data.ticket))
