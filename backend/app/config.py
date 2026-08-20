from decimal import Decimal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: str = "development"
    DATABASE_URL: str = "sqlite:///./wod_web.db"
    SECRET_KEY: str = "wod-web-development-key-change-before-production"
    CORS_ORIGINS: str = "http://127.0.0.1:9100,http://localhost:9100"
    COOKIE_SECURE: bool = False
    SESSION_TTL_DAYS: int = 14
    FRONTEND_BASE_URL: str = "http://127.0.0.1:9100"
    PUBLIC_API_BASE_URL: str = "http://127.0.0.1:8100"
    AGENT_PUBLIC_API_BASE_URL: str = ""
    AGENT_ENROLLMENT_TTL_MINUTES: int = 20
    AGENT_HEARTBEAT_OFFLINE_SECONDS: int = 120
    AGENT_AUTHORIZATION_TIMEOUT_SECONDS: int = 300
    AGENT_HARDWARE_STALE_SECONDS: int = 180
    AGENT_SERVICE_STALE_SECONDS: int = 90
    AGENT_SIGNATURE_MAX_SKEW_SECONDS: int = 300
    AGENT_REQUIRE_MTLS: bool = False
    AGENT_MTLS_PROXY_SECRET: str = ""
    AGENT_LOCAL_SIMULATOR_ENABLED: bool = True
    AGENT_ARTIFACT_ROOT: str = ""
    REDIS_URL: str = "redis://127.0.0.1:56379/0"
    NEWS_SYNC_ENABLED: bool = True
    NEWS_SYNC_INTERVAL_MINUTES: int = 30
    NEWS_SCHEDULER_STOP_TIMEOUT_SECONDS: float = 25
    NEWS_CACHE_TTL_SECONDS: int = 300
    RSSHUB_BASE_URL: str = "http://127.0.0.1:1200"
    MARKET_SNAPSHOT_ENABLED: bool = True
    MARKET_SNAPSHOT_INTERVAL_MINUTES: int = Field(default=60, ge=5, le=1440)
    MARKET_SNAPSHOT_STOP_TIMEOUT_SECONDS: float = 25
    MARKET_SNAPSHOT_HTTP_TIMEOUT_SECONDS: float = Field(default=20, ge=2, le=120)
    MARKET_SNAPSHOT_RETENTION_DAYS: int = Field(default=400, ge=30, le=3650)
    GETDEPLOYING_API_BASE_URL: str = "https://getdeploying.com/api"
    GETDEPLOYING_API_KEY: str = ""
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    SMS_PROVIDER_ENABLED: bool = False
    EMAIL_VERIFICATION_ENABLED: bool = False
    EMAIL_NOTIFICATION_ENABLED: bool = False
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_USE_TLS: bool = True
    EMAIL_VERIFICATION_TTL_HOURS: int = Field(default=24, ge=1, le=168)
    EMAIL_OUTBOX_POLL_SECONDS: int = Field(default=10, ge=2, le=300)
    EMAIL_OUTBOX_MAX_ATTEMPTS: int = Field(default=5, ge=1, le=20)
    PASSWORD_RESET_TTL_MINUTES: int = 30
    PAYMENT_PROVIDER_ENABLED: bool = False
    KYC_PROVIDER_ENABLED: bool = False
    OBJECT_STORAGE_ENABLED: bool = False
    PAYMENT_PROVIDER: str = "disabled"
    PINGXX_API_BASE_URL: str = "https://api.pingxx.com"
    PINGXX_API_KEY: str = ""
    PINGXX_APP_ID: str = ""
    PINGXX_PUBLIC_KEY: str = ""
    PINGXX_MERCHANT_PRIVATE_KEY: str = ""
    PINGXX_REQUEST_SIGNING_ENABLED: bool = False
    PINGXX_LIVE_MODE: bool = False
    PINGXX_DEFAULT_CHANNEL: str = "alipay_pc_direct"
    PINGXX_HTTP_TIMEOUT_SECONDS: float = Field(default=10, ge=2, le=60)
    PAYOUT_ENCRYPTION_KEY: str = ""
    KYC_ENCRYPTION_KEY: str = ""
    PLATFORM_COMMISSION_RATE: Decimal = Field(default=Decimal("0.05"), ge=0, lt=1)
    SETTLEMENT_HOLD_HOURS: int = Field(default=24, ge=0, le=720)
    KYC_PROVIDER: str = "disabled"
    OBJECT_STORAGE_PROVIDER: str = "disabled"
    PRIVATE_UPLOAD_MAX_BYTES: int = 20 * 1024 * 1024
    PRIVATE_UPLOAD_TTL_MINUTES: int = 15
    BUY_REQUEST_REVIEW_ENABLED: bool = False

    KAI_AUTH_ISSUER: str = "https://auth.kai.com/api/auth"
    KAI_AUTH_CLIENT_ID: str = ""
    KAI_AUTH_CLIENT_SECRET: str = ""
    KAI_AUTH_CALLBACK_URL: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def production_issues(self) -> list[str]:
        issues: list[str] = []
        if not self.DATABASE_URL.startswith(("postgresql://", "postgresql+")):
            issues.append("DATABASE_URL must use PostgreSQL")
        if len(self.SECRET_KEY) < 32 or "development" in self.SECRET_KEY or "replace" in self.SECRET_KEY:
            issues.append("SECRET_KEY must be a strong production secret")
        if not self.COOKIE_SECURE:
            issues.append("COOKIE_SECURE must be true")
        for name, value in (
            ("FRONTEND_BASE_URL", self.FRONTEND_BASE_URL),
            ("PUBLIC_API_BASE_URL", self.PUBLIC_API_BASE_URL),
            ("AGENT_PUBLIC_API_BASE_URL", self.AGENT_PUBLIC_API_BASE_URL),
        ):
            if not value.startswith("https://"):
                issues.append(f"{name} must use HTTPS")
        origins = [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]
        if not origins or any(not item.startswith("https://") for item in origins):
            issues.append("CORS_ORIGINS must contain only production HTTPS origins")
        if self.AGENT_REQUIRE_MTLS and len(self.AGENT_MTLS_PROXY_SECRET) < 32:
            issues.append("AGENT_MTLS_PROXY_SECRET must protect trusted proxy headers")
        if self.AGENT_LOCAL_SIMULATOR_ENABLED:
            issues.append("AGENT_LOCAL_SIMULATOR_ENABLED must be false")
        if not self.PAYMENT_PROVIDER_ENABLED or self.PAYMENT_PROVIDER != "pingxx":
            issues.append("Ping++ payment provider must be enabled")
        if not all((self.PINGXX_API_KEY, self.PINGXX_APP_ID, self.PINGXX_PUBLIC_KEY)):
            issues.append("Ping++ credentials are incomplete")
        if not self.PINGXX_LIVE_MODE or not self.PINGXX_API_KEY.startswith("sk_live_"):
            issues.append("Ping++ production must use Live mode and a Live Key")
        if not self.PINGXX_REQUEST_SIGNING_ENABLED or not self.PINGXX_MERCHANT_PRIVATE_KEY:
            issues.append("Ping++ production request signing must be enabled")
        if len(self.PAYOUT_ENCRYPTION_KEY) < 32:
            issues.append("PAYOUT_ENCRYPTION_KEY must protect supplier payout details")
        if len(self.KYC_ENCRYPTION_KEY) < 32:
            issues.append("KYC_ENCRYPTION_KEY must protect identity details")
        if not self.EMAIL_VERIFICATION_ENABLED:
            issues.append("EMAIL_VERIFICATION_ENABLED must be true")
        if not self.EMAIL_NOTIFICATION_ENABLED:
            issues.append("EMAIL_NOTIFICATION_ENABLED must be true")
        if not self.SMTP_HOST or not self.SMTP_FROM_EMAIL:
            issues.append("SMTP mail delivery is incomplete")
        return issues

    @model_validator(mode="after")
    def validate_production(self):
        if self.APP_ENV.casefold() == "production":
            issues = self.production_issues()
            if issues:
                raise ValueError("unsafe production configuration: " + "; ".join(issues))
        return self


settings = Settings()


def cors_origins() -> list[str]:
    return [item.strip() for item in settings.CORS_ORIGINS.split(",") if item.strip()]
