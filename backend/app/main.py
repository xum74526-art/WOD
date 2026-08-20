import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from app.config import cors_origins, settings
from app.health import database_readiness
from app.email_scheduler import email_scheduler
from app.news_scheduler import news_scheduler
from app.market_snapshot_scheduler import market_snapshot_scheduler
from app.observability import (
    ObservabilityMiddleware,
    configure_application_logging,
    render_prometheus_metrics,
)
from app.responses import fail, ok
from app.routers import (
    account,
    agents,
    admin_suppliers,
    auth,
    buy_requests,
    comments,
    integrations,
    internal_modules,
    kyc_reviews,
    news,
    orders,
    placeholders,
    public,
    quotes,
    resources,
    server_rentals,
    settlements,
    security_sessions,
)
from app.security import ApiError


configure_application_logging()
logger = logging.getLogger("app.system")


@asynccontextmanager
async def lifespan(app: FastAPI):
    started_here = news_scheduler.start()
    email_started_here = email_scheduler.start()
    market_started_here = market_snapshot_scheduler.start()
    app.state.news_scheduler = news_scheduler
    app.state.market_snapshot_scheduler = market_snapshot_scheduler
    logger.info(
        "application started",
        extra={
            "event": "application_started",
            "scheduler_running": news_scheduler.is_running,
        },
    )
    try:
        yield
    finally:
        if started_here:
            await asyncio.to_thread(news_scheduler.stop)
        if email_started_here:
            await asyncio.to_thread(email_scheduler.stop)
        if market_started_here:
            await asyncio.to_thread(market_snapshot_scheduler.stop)
        logger.info(
            "application stopped",
            extra={
                "event": "application_stopped",
                "scheduler_running": news_scheduler.is_running,
            },
        )


app = FastAPI(title="KAI Web API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(ObservabilityMiddleware)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(
        fail(exc.code, exc.message),
        status_code=exc.status_code,
        headers={"Cache-Control": "no-store", **exc.headers},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        fail("VALIDATION_ERROR", "请求参数不符合要求"),
        status_code=422,
        headers={"Cache-Control": "no-store"},
    )


app.include_router(auth.router)
app.include_router(public.router)
app.include_router(news.router)
app.include_router(comments.router)
app.include_router(integrations.router)
app.include_router(internal_modules.router)
app.include_router(kyc_reviews.router)
app.include_router(placeholders.router)
app.include_router(account.router)
app.include_router(agents.router)
app.include_router(buy_requests.router)
app.include_router(quotes.router)
app.include_router(orders.router)
app.include_router(resources.router)
app.include_router(server_rentals.router)
app.include_router(settlements.router)
app.include_router(security_sessions.router)
app.include_router(admin_suppliers.router)


@app.get("/health", tags=["system"], summary="进程存活检查")
def health(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return ok({
        "status": "healthy",
        "service": "kai-web-api",
        "news_scheduler_running": news_scheduler.is_running,
        "email_scheduler_running": email_scheduler.is_running,
        "market_snapshot_scheduler_running": market_snapshot_scheduler.is_running,
    })


@app.get(
    "/ready",
    tags=["system"],
    summary="数据库与迁移就绪检查",
    responses={503: {"description": "数据库不可达或迁移未升级到当前 head"}},
)
def ready(response: Response):
    try:
        report = database_readiness()
    except Exception:
        logger.exception(
            "readiness check failed",
            extra={"event": "readiness_check", "database_status": "not_ready"},
        )
        return JSONResponse(
            fail("SERVICE_NOT_READY", "服务依赖尚未就绪"),
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )
    response.headers["Cache-Control"] = "no-store"
    production_issues = settings.production_issues()
    return ok({
        "status": "ready",
        "service": "kai-web-api",
        **report,
        "deployment": {
            "environment": settings.APP_ENV,
            "production_ready": not production_issues,
            "blocking_issues": production_issues,
        },
    })


@app.get(
    "/metrics",
    tags=["system"],
    summary="Prometheus 基础进程指标",
    response_class=PlainTextResponse,
)
def metrics():
    return PlainTextResponse(
        render_prometheus_metrics(scheduler_running=news_scheduler.is_running),
        media_type="text/plain; version=0.0.4",
        headers={"Cache-Control": "no-store"},
    )
