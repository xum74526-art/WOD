import json
import logging
import re
import threading
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings
from app.responses import fail


REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
request_id_context: ContextVar[str] = ContextVar("wod_request_id", default="-")


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", None):
            record.request_id = request_id_context.get()
        return True


class JsonLogFormatter(logging.Formatter):
    _extra_fields = (
        "event",
        "request_id",
        "http_method",
        "http_path",
        "http_route",
        "http_status",
        "duration_ms",
        "error_code",
        "database_status",
        "migration_revision",
        "expected_revision",
        "scheduler_running",
    )

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, timezone.utc).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in self._extra_fields:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_application_logging() -> None:
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    handler = logging.StreamHandler()
    handler.addFilter(RequestContextFilter())
    if settings.LOG_FORMAT.casefold() == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s"
            )
        )

    app_logger = logging.getLogger("app")
    app_logger.handlers.clear()
    app_logger.addHandler(handler)
    app_logger.setLevel(level)
    app_logger.propagate = False

    # Application access logs below contain the same information in a stable,
    # structured shape, so Uvicorn's second plain-text access line is redundant.
    logging.getLogger("uvicorn.access").disabled = True


class HttpMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = time.time()
        self._started_monotonic = time.monotonic()
        self._requests_total = 0
        self._requests_in_flight = 0
        self._responses_4xx_total = 0
        self._responses_5xx_total = 0
        self._duration_seconds_sum = 0.0

    def request_started(self) -> None:
        with self._lock:
            self._requests_in_flight += 1

    def request_finished(self, status_code: int, duration_seconds: float) -> None:
        with self._lock:
            self._requests_in_flight = max(0, self._requests_in_flight - 1)
            self._requests_total += 1
            self._duration_seconds_sum += duration_seconds
            if 400 <= status_code < 500:
                self._responses_4xx_total += 1
            elif status_code >= 500:
                self._responses_5xx_total += 1

    def snapshot(self) -> dict[str, int | float]:
        with self._lock:
            return {
                "process_started_at_seconds": self._started_at,
                "process_uptime_seconds": max(0.0, time.monotonic() - self._started_monotonic),
                "http_requests_total": self._requests_total,
                "http_requests_in_flight": self._requests_in_flight,
                "http_responses_4xx_total": self._responses_4xx_total,
                "http_responses_5xx_total": self._responses_5xx_total,
                "http_request_duration_seconds_sum": self._duration_seconds_sum,
            }


http_metrics = HttpMetrics()
access_logger = logging.getLogger("app.http")


def _request_id(headers: Headers) -> str:
    candidate = headers.get(REQUEST_ID_HEADER, "")
    if _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


class ObservabilityMiddleware:
    def __init__(self, app: ASGIApp, metrics: HttpMetrics = http_metrics) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id(Headers(scope=scope))
        scope.setdefault("state", {})["request_id"] = request_id
        context_token = request_id_context.set(request_id)
        started_at = time.perf_counter()
        status_code = 500
        response_started = False
        self.metrics.request_started()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_started = True
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            try:
                await self.app(scope, receive, send_with_request_id)
            except Exception:
                access_logger.exception(
                    "unhandled request exception",
                    extra={
                        "event": "http_request_exception",
                        "http_method": scope.get("method"),
                        "http_path": scope.get("path"),
                        "http_status": 500,
                    },
                )
                if response_started:
                    raise
                response = JSONResponse(
                    fail("INTERNAL_SERVER_ERROR", "服务器暂时无法处理该请求"),
                    status_code=500,
                    headers={"Cache-Control": "no-store"},
                )
                await response(scope, receive, send_with_request_id)
        finally:
            duration_seconds = time.perf_counter() - started_at
            self.metrics.request_finished(status_code, duration_seconds)
            route = scope.get("route")
            route_path = getattr(route, "path", None)
            access_logger.info(
                "request completed",
                extra={
                    "event": "http_request",
                    "http_method": scope.get("method"),
                    "http_path": scope.get("path"),
                    "http_route": route_path,
                    "http_status": status_code,
                    "duration_ms": round(duration_seconds * 1000, 3),
                },
            )
            request_id_context.reset(context_token)


def render_prometheus_metrics(*, scheduler_running: bool) -> str:
    values = http_metrics.snapshot()
    lines = [
        "# HELP wod_process_started_at_seconds Unix timestamp when the API process started.",
        "# TYPE wod_process_started_at_seconds gauge",
        f"wod_process_started_at_seconds {values['process_started_at_seconds']:.3f}",
        "# HELP wod_process_uptime_seconds API process uptime in seconds.",
        "# TYPE wod_process_uptime_seconds gauge",
        f"wod_process_uptime_seconds {values['process_uptime_seconds']:.6f}",
        "# HELP wod_http_requests_total Completed HTTP requests.",
        "# TYPE wod_http_requests_total counter",
        f"wod_http_requests_total {values['http_requests_total']}",
        "# HELP wod_http_requests_in_flight HTTP requests currently being handled.",
        "# TYPE wod_http_requests_in_flight gauge",
        f"wod_http_requests_in_flight {values['http_requests_in_flight']}",
        "# HELP wod_http_responses_4xx_total Completed HTTP responses with a 4xx status.",
        "# TYPE wod_http_responses_4xx_total counter",
        f"wod_http_responses_4xx_total {values['http_responses_4xx_total']}",
        "# HELP wod_http_responses_5xx_total Completed HTTP responses with a 5xx status.",
        "# TYPE wod_http_responses_5xx_total counter",
        f"wod_http_responses_5xx_total {values['http_responses_5xx_total']}",
        "# HELP wod_http_request_duration_seconds_sum Total HTTP request duration.",
        "# TYPE wod_http_request_duration_seconds_sum counter",
        f"wod_http_request_duration_seconds_sum {values['http_request_duration_seconds_sum']:.6f}",
        "# HELP wod_news_scheduler_running Whether the in-process news scheduler is running.",
        "# TYPE wod_news_scheduler_running gauge",
        f"wod_news_scheduler_running {1 if scheduler_running else 0}",
    ]
    return "\n".join(lines) + "\n"
