"""Route-scoped request body limits applied before FastAPI buffers JSON."""

from fastapi import HTTPException
from fastapi.routing import APIRoute
from starlette.types import Message, Receive, Scope, Send


REGISTRATION_BODY_MAX_BYTES = 16 * 1024
REGISTRATION_BODY_TOO_LARGE_MESSAGE = "注册信息过长，请缩短后重试"


def _declared_content_length(scope: Scope) -> int | None:
    """Return a trustworthy non-negative Content-Length when one is present."""

    for name, value in scope.get("headers", ()):
        if name.lower() != b"content-length":
            continue
        try:
            length = int(value)
        except (TypeError, ValueError):
            return None
        return length if length >= 0 else None
    return None


class RegistrationBodyLimitRoute(APIRoute):
    """Reject oversized registration JSON before request.body() buffers it."""

    max_body_bytes = REGISTRATION_BODY_MAX_BYTES

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        declared_length = _declared_content_length(scope)
        if declared_length is not None and declared_length > self.max_body_bytes:
            raise HTTPException(
                status_code=413,
                detail=REGISTRATION_BODY_TOO_LARGE_MESSAGE,
            )

        received_bytes = 0

        async def limited_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_body_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=REGISTRATION_BODY_TOO_LARGE_MESSAGE,
                    )
            return message

        await super().handle(scope, limited_receive, send)
