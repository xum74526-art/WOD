from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import HTTPException as FastAPIHTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_cors_origins, settings
from app.core.sensitive import assert_sensitive_capabilities_secure
from app.routers import address, asset, auth, bank_card, buy_request, chat, community, coupon, finance, invite, market, notification, offline_purchase, onboarding, order, payment, product, qixiang_payment, revenue, supplier, user, verification, wallet, withdrawal
from app.services.lifecycle import expire_due
from app.services.offer_sync import sync_offers
from app.services.market_sync import cleanup_market_history, dispatch_market_sync, sync_market
from app.services.market_history_sync import sync_market_history
from app.services.rebate_settle import settle_rebate
from app.services.revenue_settle import INTERVAL_SECONDS, settle_revenue
from app.services.notification_service import sync_operational_notifications
from app.utils.response import BizError, error


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Never start PII-bearing capabilities with the source default JWT secret
    # or without a separate valid Fernet key.
    assert_sensitive_capabilities_secure()
    try:
        community_timezone = ZoneInfo(settings.COMMUNITY_TIMEZONE)
    except ZoneInfoNotFoundError:
        community_timezone = timezone(timedelta(hours=8))
    scheduler = BackgroundScheduler(timezone=community_timezone)
    # 收益结算：为活跃资产产生每日收益（基于 daily_rate）
    scheduler.add_job(settle_revenue, "interval", seconds=INTERVAL_SECONDS, id="settle_revenue")
    scheduler.add_job(expire_due, "interval", seconds=60, id="expire_due")
    scheduler.add_job(sync_offers, "interval", seconds=300, id="sync_offers")
    scheduler.add_job(
        dispatch_market_sync,
        "interval",
        seconds=settings.MARKET_SYNC_SECONDS,
        id="sync_market",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(cleanup_market_history, "interval", hours=6, id="cleanup_market_history", replace_existing=True)
    if settings.MARKET_HISTORY_SYNC_ENABLED:
        scheduler.add_job(
            sync_market_history,
            "interval",
            seconds=max(settings.MARKET_HISTORY_REFRESH_SECONDS, 300),
            id="sync_market_history",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
    scheduler.add_job(settle_rebate, "interval", seconds=300, id="settle_rebate")
    # First-party inbox event synchronization. This does not claim or require
    # native OS push delivery; each event is idempotent through a dedupe key.
    scheduler.add_job(
        sync_operational_notifications,
        "interval",
        seconds=30,
        id="sync_in_app_notifications",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    # 每日社区内容更新
    from app.services.community_daily import generate_daily_posts
    scheduler.add_job(
        generate_daily_posts,
        "cron",
        hour=settings.COMMUNITY_PUBLISH_HOUR,
        minute=settings.COMMUNITY_PUBLISH_MINUTE,
        id="community_daily",
        kwargs={"count": settings.COMMUNITY_DAILY_TARGET},
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        sync_market,
        "date",
        run_date=datetime.now(community_timezone) + timedelta(seconds=1),
        id="market_startup_sync",
        kwargs={"force": True},
        replace_existing=True,
    )
    if settings.MARKET_HISTORY_SYNC_ENABLED:
        scheduler.add_job(
            sync_market_history,
            "date",
            run_date=datetime.now(community_timezone) + timedelta(seconds=5),
            id="market_history_startup_sync",
            kwargs={"force": True},
            replace_existing=True,
        )
    scheduler.add_job(
        sync_operational_notifications,
        "date",
        run_date=datetime.now(community_timezone) + timedelta(seconds=4),
        id="notification_startup_sync",
        replace_existing=True,
    )
    # Refresh provider-backed product cards at startup as well; otherwise an
    # expired card can remain hidden for the first five minutes after restart.
    scheduler.add_job(
        sync_offers,
        "date",
        run_date=datetime.now(community_timezone) + timedelta(seconds=2),
        id="offer_startup_sync",
        replace_existing=True,
    )
    # 启动后自动补齐当天缺口；任务自身幂等，不会重复发布。
    scheduler.add_job(
        generate_daily_posts,
        "date",
        run_date=datetime.now(community_timezone) + timedelta(seconds=3),
        id="community_startup_catchup",
        kwargs={"count": settings.COMMUNITY_DAILY_TARGET},
        replace_existing=True,
    )
    scheduler.start()
    print(
        f"[KAI API] 定时任务已启动: 收益每 {INTERVAL_SECONDS}s / 到期每 60s / "
        f"社区每天 {settings.COMMUNITY_PUBLISH_HOUR:02d}:{settings.COMMUNITY_PUBLISH_MINUTE:02d} "
        f"补齐 {settings.COMMUNITY_DAILY_TARGET} 条"
    )
    yield
    scheduler.shutdown()


app = FastAPI(title="KAI API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(BizError)
async def biz_handler(request: Request, exc: BizError):
    return JSONResponse(status_code=exc.status_code, content=error(exc.msg, exc.code))


@app.exception_handler(FastAPIHTTPException)
async def http_handler(request: Request, exc: FastAPIHTTPException):
    msg = exc.detail if isinstance(exc.detail, str) else "请求错误"
    return JSONResponse(status_code=exc.status_code, content=error(msg))


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError):
    # Consent is intentionally a required strict boolean in the public schema.
    # Convert the otherwise-generic FastAPI 422 into an explicit client error
    # so old clients cannot silently submit identity documents without it.
    is_verification_submit = (
        request.method.upper() == "POST"
        and request.url.path.rstrip("/") == "/api/verification"
    )
    consent_error = any(
        error_item.get("loc", ())[-1:] == ("sensitive_consent",)
        for error_item in exc.errors()
    )
    if is_verification_submit and consent_error:
        return JSONResponse(
            status_code=400,
            content=error("请先单独同意身份证敏感信息用于本地文字识别和人工审核"),
        )
    return await request_validation_exception_handler(request, exc)


app.include_router(auth.router)
app.include_router(user.router)
app.include_router(product.router)
app.include_router(market.router)
app.include_router(asset.router)
app.include_router(order.router)
app.include_router(wallet.router)
app.include_router(withdrawal.router)
app.include_router(finance.router)
app.include_router(payment.router)
app.include_router(qixiang_payment.router)
app.include_router(revenue.router)
app.include_router(notification.router)
app.include_router(verification.router)
app.include_router(bank_card.router)
app.include_router(invite.router)
app.include_router(coupon.router)
app.include_router(address.router)
app.include_router(offline_purchase.router)
app.include_router(buy_request.router)
app.include_router(onboarding.router)
app.include_router(supplier.router)
app.include_router(community.router)
app.include_router(community.public_router)
app.include_router(chat.router)

@app.get("/")
def health():
    return {"code": 0, "msg": "KAI API running", "data": None}


@app.get("/health")
def health2():
    return {"code": 0, "msg": "ok", "data": {"status": "healthy"}}
