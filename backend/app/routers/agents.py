from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.agent_schemas import (
    AgentCommandResultIn,
    AgentEnrollIn,
    AgentEnrollmentCreateIn,
    AgentHeartbeatIn,
)
from app.db import get_db
from app.models import MerchantServer, User
from app.responses import ok
from app.security import require_csrf
from app.services import agents as service
from app.services import server_rentals


router = APIRouter(prefix="/api/v1", tags=["agent"])


async def require_agent(
    request: Request,
    x_agent_id: Annotated[str | None, Header(alias="X-KAI-Agent-ID")] = None,
    x_agent_timestamp: Annotated[str | None, Header(alias="X-KAI-Timestamp")] = None,
    x_agent_nonce: Annotated[str | None, Header(alias="X-KAI-Nonce")] = None,
    x_agent_signature: Annotated[str | None, Header(alias="X-KAI-Signature")] = None,
    x_client_cert_fingerprint: Annotated[
        str | None, Header(alias="X-Client-Cert-Fingerprint")
    ] = None,
    x_kai_mtls_proxy_secret: Annotated[
        str | None, Header(alias="X-KAI-MTLS-Proxy-Secret")
    ] = None,
    db: Session = Depends(get_db),
) -> MerchantServer:
    body = await request.body()
    return service.authenticate_agent(
        db,
        agent_id=x_agent_id or "",
        timestamp=x_agent_timestamp or "",
        nonce=x_agent_nonce or "",
        signature=x_agent_signature or "",
        method=request.method,
        path=request.url.path,
        body=body,
        client_cert_fingerprint=x_client_cert_fingerprint,
        mtls_proxy_secret=x_kai_mtls_proxy_secret,
    )


@router.get("/agent/downloads")
def list_downloads(request: Request):
    base_url = service.api_base_url(str(request.base_url))
    return ok(service.downloads(base_url), {"version": service.AGENT_VERSION})


@router.get("/agent/downloads/{platform}/{arch}")
def download_agent(platform: str, arch: str):
    path = service.download_path(platform, arch)
    return FileResponse(
        path,
        media_type=("application/gzip" if platform == "docker" else
        "application/vnd.microsoft.portable-executable" if platform == "windows"
        else "application/octet-stream"),
        filename=path.name,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/agent/install/linux", response_class=PlainTextResponse)
def linux_installer():
    path = service.INSTALL_ROOT / "install.sh"
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/x-shellscript")


@router.get("/agent/install/windows", response_class=PlainTextResponse)
def windows_installer():
    path = service.INSTALL_ROOT / "install.ps1"
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/plain")


@router.post("/supplier/servers/{server_id}/enrollment-token", status_code=status.HTTP_201_CREATED)
def create_enrollment_token(
    server_id: int,
    data: AgentEnrollmentCreateIn,
    request: Request,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    base_url = service.api_base_url(str(request.base_url))
    return ok(service.create_enrollment(
        db,
        user,
        server_id,
        expires_in_minutes=data.expires_in_minutes,
        base_url=base_url,
    ))


@router.post("/agent/enroll", status_code=status.HTTP_201_CREATED)
def enroll_agent(
    data: AgentEnrollIn,
    response: Response,
    x_client_cert_fingerprint: Annotated[
        str | None, Header(alias="X-Client-Cert-Fingerprint")
    ] = None,
    x_kai_mtls_proxy_secret: Annotated[
        str | None, Header(alias="X-KAI-MTLS-Proxy-Secret")
    ] = None,
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return ok(service.enroll_agent(
        db,
        data,
        client_cert_fingerprint=x_client_cert_fingerprint,
        mtls_proxy_secret=x_kai_mtls_proxy_secret,
    ))


@router.post("/agent/heartbeat")
def heartbeat(
    data: AgentHeartbeatIn,
    response: Response,
    server: MerchantServer = Depends(require_agent),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    server_rentals.process_due_leases(db)
    return ok(service.heartbeat(db, server, data))


@router.get("/agent/commands/next")
def next_command(
    response: Response,
    server: MerchantServer = Depends(require_agent),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    server_rentals.process_due_leases(db)
    return ok(service.claim_command(db, server), {"retry_after_seconds": 5})


@router.post("/agent/commands/{command_no}/result")
def command_result(
    command_no: str,
    data: AgentCommandResultIn,
    response: Response,
    server: MerchantServer = Depends(require_agent),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    command = service.complete_command(
        db,
        server,
        command_no,
        success=data.success,
        message=data.message,
    )
    return ok(service.command_result_out(command))
