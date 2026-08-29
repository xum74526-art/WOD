from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "wod-dev-secret-key-change-in-production-9f8a7b6c5d4e3f2a1b0c"


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./wod.db"  # 本地默认 SQLite；生产可配置 PostgreSQL URL
    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    # Stable public client identifiers mapped to server-owned source labels.
    # Clients submit only an identifier; arbitrary platform headers are never
    # used for attribution. Unknown identifiers are rejected, while omitted
    # identifiers remain "legacy" during the installed-client transition.
    AUTH_CLIENT_PLATFORM_MAP: str = "web=web,ios=ios,android=android,admin=admin"
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
    # Direct checkout and other in-app transaction commitments stay disabled
    # until the required company qualifications and payment rails are ready.
    # Inquiry submission and human follow-up remain available independently.
    DIRECT_TRADE_ENABLED: bool = False
    # Demand publication, supplier quoting and platform coordination are a
    # separate capability from wallet-backed direct trade. Keep this enabled
    # for the qualification-pending launch so clients can submit enquiries
    # while every financial commitment remains fail-closed.
    MATCHMAKING_ENABLED: bool = True
    # Structured SSH delivery is an independently switchable, server-enforced
    # matchmaking capability. Payloads are encrypted with the application's
    # sensitive-data key and are never written to orders, events or logs.
    MATCHMAKING_CREDENTIAL_ESCROW_ENABLED: bool = True
    # Keep payment actions visible but do not simulate money movement before a
    # real payment and settlement provider has been connected.
    PAYMENT_SERVICE_ENABLED: bool = False
    # Recharge, bank-card verification, and payout are separate capabilities.
    # Enabling the MaPay collection gateway must never silently enable either
    # bank-card collection or money transfers.
    # Internal manual bank-card review and payout workflow. These switches
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
    PAYOUT_MIN_CARD_HOURS: float = 10.0
    PAYOUT_MAX_CARD_HOURS: float = 100000.0
    PAYOUT_RECEIPT_MAX_BYTES: int = 5 * 1024 * 1024
    # Full payout instructions are sensitive. Finance must use the short-lived,
    # one-time proof returned by the reveal endpoint when recording a payment.
    PAYOUT_INSTRUCTION_REVEAL_TTL_SECONDS: int = 300
    # Confirmed WOD merchant sales settle independently from promotional
    # reward card-hours and synthetic asset revenue. Ten percent = 1000 bps.
    MERCHANT_SERVICE_FEE_BPS: int = 1000
    # Reserved order funds cannot remain frozen forever. Pending delivery is
    # refunded, a delivered order auto-confirms if the buyer raises no dispute,
    # and an unresolved dispute defaults to a buyer refund after the SLA.
    ORDER_DELIVERY_TIMEOUT_HOURS: int = 24
    ORDER_CONFIRMATION_TIMEOUT_HOURS: int = 24
    ORDER_DISPUTE_REVIEW_TIMEOUT_HOURS: int = 72
    # Existing pending/delivering rows may reflect manual agreements. They are
    # never auto-migrated into the new SLA until operations explicitly opts in.
    ORDER_LEGACY_PENDING_MIGRATION_ENABLED: bool = False
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
    MAPAY_MIN_AMOUNT_CNY: float = 10.0
    MAPAY_MAX_AMOUNT_CNY: float = 50000.0
    # QiXiang Pay (EasyPay-compatible) wallet recharge collection. Keep the
    # provider disabled until the public HTTPS notify/return URLs are deployed.
    QIXIANGPAY_ENABLED: bool = False
    QIXIANGPAY_BASE_URL: str = "https://api.payqixiang.cn"
    QIXIANGPAY_PID: str = ""
    QIXIANGPAY_KEY: str = ""
    QIXIANGPAY_NOTIFY_URL: str = ""
    QIXIANGPAY_RETURN_URL: str = ""
    # Optional public API origin (normally ending in /api) used to return an
    # absolute first-party checkout URL to native clients.
    QIXIANGPAY_PUBLIC_API_BASE_URL: str = ""
    QIXIANGPAY_PAYMENT_TYPES: str = ""
    QIXIANGPAY_DEVICE: str = "jump"
    QIXIANGPAY_HTTP_TIMEOUT: float = 10.0
    QIXIANGPAY_MAX_RESPONSE_BYTES: int = 256 * 1024
    # Forwarded client IP headers are accepted only from these immediate peers.
    QIXIANGPAY_TRUSTED_PROXY_CIDRS: str = "127.0.0.1/32,::1/128"
    QIXIANGPAY_CHECKOUT_TTL_SECONDS: int = 300
    QIXIANGPAY_PROVIDER_TIMEZONE: str = "Asia/Shanghai"
    QIXIANGPAY_MIN_AMOUNT_CNY: float = 10.0
    QIXIANGPAY_MAX_AMOUNT_CNY: float = 50000.0
    # Disabled until metered compute output and an auditable settlement source
    # are connected. Never create wallet income from a configured percentage.
    REVENUE_SETTLEMENT_ENABLED: bool = False
    # Registration/invite/consumer/supplier rebates remain disabled until an
    # auditable verification and settlement policy is connected.
    REWARD_SERVICE_ENABLED: bool = False
    # In-app card-hour rewards are spendable only inside WOD and are always
    # non-withdrawable, independently of recharge or payout configuration.
    # They use dedicated ledger types so legacy synthetic rewards stay excluded.
    CLOSED_TEST_REWARD_ENABLED: bool = False
    # Versioned reward programs are deliberately independent. Enabling one
    # never activates legacy reward ledger rows or either of the other
    # programs. Existing deployments must opt in to each writer explicitly.
    CONSUMER_REWARD_ENABLED: bool = False
    SUPPLIER_REWARD_ENABLED: bool = False
    INVITE_REWARD_ENABLED: bool = False
    # Invitation V2 is independent from the retired first-order percentage
    # writer. It uses verified identity, daily qualification slots and
    # cash-backed consumption snapshots.
    INVITE_V2_ENABLED: bool = False
    # Emergency settlement pause. Program switches above stop new accruals;
    # this separate switch controls payment of already-promised accruals.
    REWARD_SETTLEMENT_ENABLED: bool = False
    REWARD_TIMEZONE: str = "Asia/Shanghai"
    # Station/in-app messages work without an external provider. Native push
    # stays explicitly unavailable until deployment enables a provider.
    PUSH_SERVICE_ENABLED: bool = False
    PUSH_PROVIDER: str = ""
    # KAI Pricing is the only active third-party market source.  It publishes
    # native CNY prices per GPU-hour and does not require provider credentials.
    KAI_PRICING_API_BASE_URL: str = "https://pricing.kai.com"
    KAI_PRICING_REFRESH_SECONDS: int = 300
    KAI_PRICING_HTTP_TIMEOUT: float = 10.0
    KAI_PRICING_MAX_RESPONSE_BYTES: int = 2 * 1024 * 1024
    # Keep idle sockets shorter than the five-minute publication cadence and
    # reserve bounded time for httpcore to close a cancelled response.  If a
    # generation still cannot unwind, the runner may quarantine one old pool
    # and atomically publish a fresh client; restart rate limits prevent leaks.
    KAI_PRICING_HTTP_KEEPALIVE_SECONDS: float = 30.0
    KAI_PRICING_HTTP_CLEANUP_GRACE: float = 0.75
    KAI_PRICING_HTTP_MAX_RETIRED_GENERATIONS: int = 1
    KAI_PRICING_HTTP_RESTART_LIMIT: int = 3
    KAI_PRICING_HTTP_RESTART_WINDOW_SECONDS: int = 300
    # A second independently wedged generation cannot be healed safely inside
    # one process without leaking connection pools.  The production unit is
    # supervised with Restart=always, so escalate only after this grace period.
    KAI_PRICING_HTTP_FAIL_FAST_ENABLED: bool = False
    KAI_PRICING_HTTP_FAIL_FAST_SECONDS: float = 30.0
    KAI_CANDLE_HTTP_TIMEOUT: float = 6.0
    KAI_CANDLE_TOTAL_TIMEOUT: float = 15.0
    KAI_CANDLE_MAX_RESPONSE_BYTES: int = 1024 * 1024
    KAI_CANDLE_MAX_TOTAL_BYTES: int = 6 * 1024 * 1024
    KAI_CANDLE_MAX_PRODUCTS: int = 8
    KAI_RANKING_MAX_PRODUCTS: int = 24
    KAI_CANDLE_MAX_WORKERS: int = 4
    KAI_CANDLE_CACHE_SECONDS: int = 300
    # KAI exposes a maximum configurable GPU count, not live inventory.  This
    # separate cap is the only stock that the manual fulfilment workflow may
    # reserve and restore.
    KAI_CLOSED_TEST_INITIAL_STOCK: int = 3
    # The API is the sole market-database writer. External collectors submit
    # normalized batches through an authenticated internal endpoint.
    MARKET_INGESTION_ENABLED: bool = False
    MARKET_INGESTION_TOKEN: str = ""
    VAST_STALE_SECONDS: int = 1800
    VAST_DELETE_AFTER_HOURS: int = 48
    VAST_HISTORY_DAYS: int = 90
    MARKET_SYNC_SECONDS: int = 10
    MARKET_HISTORY_DAYS: int = 30
    # KAI publishes current-price revisions on a five-minute validity window.
    # Persist each new publication, including an unchanged price, without
    # requesting the provider faster than its documented cadence.
    MARKET_UNCHANGED_SNAPSHOT_SECONDS: int = 300
    MARKET_CANDLE_SYNC_SECONDS: int = 300
    MARKET_CANDLE_HISTORY_DAYS: int = 100
    PRODUCT_OFFER_MAX_AGE_SECONDS: int = 900
    # Authenticated users allowed to fulfil KAI-backed manually delivered orders.
    # Use comma-separated numeric user IDs.  KAI purchases fail closed when no
    # configured ID resolves to an existing fulfilment operator account.
    PLATFORM_FULFILLMENT_USER_IDS: str = ""
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

    # Ignore retired AutoDL keys that may remain temporarily in a private
    # deployment environment during a rolling upgrade.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()


def get_cors_origins() -> list[str]:
    return [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
