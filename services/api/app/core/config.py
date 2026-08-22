from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "wod-dev-secret-key-change-in-production-9f8a7b6c5d4e3f2a1b0c"


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./wod.db"  # 本地默认 SQLite；生产可配置 PostgreSQL URL
    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174,http://localhost:9000"
    # Sensitive fields are encrypted at rest. Set a dedicated Fernet key in
    # production; local development falls back to a key derived from SECRET_KEY.
    SENSITIVE_DATA_KEY: str = ""
    # Empty uses backend/uploads locally. Containers set this to a persistent
    # private volume such as /data/uploads.
    UPLOAD_ROOT: str = ""
    ID_PHOTO_MAX_BYTES: int = 5 * 1024 * 1024
    # Local ID-card text recognition is an OCR pre-check only.  It never marks
    # an account verified; a finance operator must still review the documents.
    # Keep disabled until the server image contains Tesseract with chi_sim.
    ID_OCR_ENABLED: bool = False
    ID_OCR_TESSERACT_CMD: str = "tesseract"
    ID_OCR_LANGUAGES: str = "chi_sim+eng"
    ID_OCR_TIMEOUT_SECONDS: float = 10.0
    ID_OCR_QUEUE_TIMEOUT_SECONDS: float = 2.0
    ID_OCR_MAX_CONCURRENCY: int = 2
    ID_OCR_MAX_PIXELS: int = 20_000_000
    ID_OCR_MAX_OUTPUT_CHARS: int = 50_000
    AVATAR_MAX_BYTES: int = 2 * 1024 * 1024
    COMMUNITY_IMAGE_MAX_BYTES: int = 5 * 1024 * 1024
    COMMUNITY_VIDEO_MAX_BYTES: int = 50 * 1024 * 1024
    # Keep payment actions visible but do not simulate money movement before a
    # real payment and settlement provider has been connected.
    PAYMENT_SERVICE_ENABLED: bool = False
    # Recharge, bank-card verification, and payout are separate capabilities.
    # Enabling the MaPay collection gateway must never silently enable either
    # bank-card collection or money transfers.
    # Closed-test manual bank-card review and payout workflow.  These switches
    # are intentionally independent from collection gateways and future
    # automated payout providers.  Both default to off so a deployment cannot
    # begin collecting card details or accepting withdrawal requests merely by
    # enabling wallet recharge.
    MANUAL_BANK_CARD_ENABLED: bool = False
    MANUAL_PAYOUT_ENABLED: bool = False
    # Finance operators are explicit user IDs, never inferred from the supplier
    # role or the order-fulfilment allow-list.
    FINANCE_ADMIN_USER_IDS: str = ""
    PAYOUT_CARD_HOUR_RMB_RATE: float = 1.002
    PAYOUT_FEE_RATE: float = 0.0
    PAYOUT_MIN_CARD_HOURS: float = 1.0
    PAYOUT_MAX_CARD_HOURS: float = 100000.0
    PAYOUT_RECEIPT_MAX_BYTES: int = 5 * 1024 * 1024
    # Full payout instructions are sensitive. Finance must use the short-lived,
    # one-time proof returned by the reveal endpoint when recording a payment.
    PAYOUT_INSTRUCTION_REVEAL_TTL_SECONDS: int = 300
    CARD_HOUR_RMB_RATE: float = 1.002
    MAPAY_ENABLED: bool = False
    MAPAY_BASE_URL: str = "https://mzf.mapay.cc/xpay/epayn"
    MAPAY_PID: str = ""
    MAPAY_MERCHANT_PRIVATE_KEY_PATH: str = ""
    MAPAY_PLATFORM_PUBLIC_KEY_PATH: str = ""
    MAPAY_NOTIFY_URL: str = ""
    MAPAY_PUBLIC_API_BASE_URL: str = ""
    # Comma-separated channels verified as usable for this merchant account.
    # Keep empty until each channel has passed a real provider-side check.
    MAPAY_PAYMENT_TYPES: str = ""
    MAPAY_HTTP_TIMEOUT: float = 10.0
    # MaPay hosted orders expire after roughly five minutes.  WOD uses the
    # same deadline so it never presents an already-invalid checkout as open.
    MAPAY_CHECKOUT_TTL_SECONDS: int = 300
    # Human-readable MaPay addtime/endtime values use the provider timezone.
    MAPAY_PROVIDER_TIMEZONE: str = "Asia/Shanghai"
    MAPAY_MIN_AMOUNT_CNY: float = 0.01
    MAPAY_MAX_AMOUNT_CNY: float = 50000.0
    # QiXiang Pay (EasyPay-compatible) wallet recharge collection. Keep the
    # provider disabled until the public HTTPS notify/return URLs are deployed.
    QIXIANGPAY_ENABLED: bool = False
    QIXIANGPAY_BASE_URL: str = "https://api.payqixiang.cn"
    QIXIANGPAY_PID: str = ""
    QIXIANGPAY_KEY: str = ""
    QIXIANGPAY_NOTIFY_URL: str = ""
    QIXIANGPAY_RETURN_URL: str = ""
    QIXIANGPAY_PAYMENT_TYPES: str = ""
    QIXIANGPAY_DEVICE: str = "jump"
    QIXIANGPAY_HTTP_TIMEOUT: float = 10.0
    QIXIANGPAY_CHECKOUT_TTL_SECONDS: int = 300
    QIXIANGPAY_MIN_AMOUNT_CNY: float = 0.01
    QIXIANGPAY_MAX_AMOUNT_CNY: float = 50000.0
    # Disabled until metered compute output and an auditable settlement source
    # are connected. Never create wallet income from a configured percentage.
    REVENUE_SETTLEMENT_ENABLED: bool = False
    # Registration/invite/consumer/supplier rebates remain disabled until an
    # auditable verification and settlement policy is connected.
    REWARD_SERVICE_ENABLED: bool = False
    # Closed-test card-hour rewards are spendable only inside WOD and remain
    # non-withdrawable while PAYMENT_SERVICE_ENABLED is false.  They use
    # dedicated ledger types so legacy synthetic rewards stay excluded.
    CLOSED_TEST_REWARD_ENABLED: bool = False
    # Station/in-app messages work without an external provider. Native push
    # stays explicitly unavailable until deployment enables a provider.
    PUSH_SERVICE_ENABLED: bool = False
    PUSH_PROVIDER: str = ""
    VAST_API_KEY: str = ""
    VAST_API_BASE_URL: str = "https://console.vast.ai/api/v0"
    USD_CNY_RATE: float = 7.2
    AUTODL_TOKEN: str = ""
    AUTODL_API_BASE_URL: str = "https://api.autodl.com"
    MARKET_SYNC_SECONDS: int = 10
    VAST_MARKET_REFRESH_SECONDS: int = 30
    AUTODL_MARKET_REFRESH_SECONDS: int = 60
    WOD_MARKET_REFRESH_SECONDS: int = 10
    MARKET_HISTORY_DAYS: int = 30
    MARKET_UNCHANGED_SNAPSHOT_SECONDS: int = 3600
    # Real seven-day market history. The official Vast endpoint is attempted
    # first; the public CC BY 4.0 dataset is an attributed fallback/backfill.
    # Downloads happen only in a scheduled background job, never in API
    # request handlers.
    MARKET_HISTORY_SYNC_ENABLED: bool = True
    MARKET_HISTORY_REFRESH_SECONDS: int = 21600
    MARKET_HISTORY_BACKFILL_DAYS: int = 10
    MARKET_HISTORY_HTTP_TIMEOUT: float = 20.0
    MARKET_HISTORY_CACHE_ROOT: str = ""
    MARKET_HISTORY_MAX_FILE_BYTES: int = 5 * 1024 * 1024
    MARKET_HISTORY_MAX_REFRESH_BYTES: int = 25 * 1024 * 1024
    MARKET_HISTORY_MIN_EXTERNAL_SAMPLES_PER_DAY: int = 3
    MARKET_HISTORY_HF_DATASET: str = "afhubbard/gpu-prices"
    MARKET_HISTORY_HF_LICENSE: str = "CC BY 4.0"
    PRODUCT_OFFER_MAX_AGE_SECONDS: int = 900
    # Authenticated users allowed to fulfil provider-backed closed-test orders.
    # Use comma-separated numeric user IDs.  An empty value means that external
    # orders can be purchased and cancelled, but only remain pending delivery.
    PLATFORM_FULFILLMENT_USER_IDS: str = ""
    FX_API_URL: str = "https://api.frankfurter.dev/v2/rate/USD/CNY?providers=ECB"
    FX_REFRESH_SECONDS: int = 21600
    # Support AI adapter. Empty provider/key keeps the built-in FAQ and durable
    # ticket service fully usable in truthful "self_service" mode.
    AI_PROVIDER: str = ""
    AI_API_KEY: str = ""
    AI_BASE_URL: str = ""
    AI_MODEL: str = ""
    AI_HTTP_TIMEOUT: float = 20.0
    # Legacy DeepSeek-compatible fields remain supported for existing servers.
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = ""
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"
    # 社区每日公开资讯（全部来源均需在代码白名单内）
    COMMUNITY_ONLINE_ENABLED: bool = True
    COMMUNITY_DAILY_TARGET: int = 10
    COMMUNITY_DAILY_VIDEO_TARGET: int = 5
    COMMUNITY_PUBLISH_HOUR: int = 8
    COMMUNITY_PUBLISH_MINUTE: int = 30
    COMMUNITY_TIMEZONE: str = "Asia/Shanghai"
    COMMUNITY_HTTP_TIMEOUT: float = 10.0
    # Kai OAuth 2.1 / OpenID Connect. Credentials and redirect addresses must
    # be supplied by deployment environment variables; empty values disable it.
    KAI_AUTH_ISSUER: str = ""
    KAI_AUTH_CLIENT_ID: str = ""
    KAI_AUTH_CLIENT_SECRET: str = ""
    KAI_AUTH_CALLBACK_URL: str = ""
    KAI_AUTH_APP_RETURN_URL: str = ""
    # Exact, comma-separated browser/app return URLs allowed to start a Kai
    # flow. The legacy APP_RETURN_URL remains the default and is always allowed.
    KAI_AUTH_ALLOWED_RETURN_URLS: str = ""
    KAI_AUTH_SCOPES: str = "openid profile email"
    KAI_AUTH_FLOW_TTL_SECONDS: int = 600
    KAI_AUTH_TICKET_TTL_SECONDS: int = 120
    KAI_AUTH_HTTP_TIMEOUT: float = 10.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()


def get_cors_origins() -> list[str]:
    return [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
