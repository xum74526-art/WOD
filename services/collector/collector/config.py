from pydantic_settings import BaseSettings, SettingsConfigDict


class CollectorSettings(BaseSettings):
    INGESTION_API_URL: str = "http://127.0.0.1:8001/internal/v1/ingestion/market-offers/batches"
    INGESTION_TOKEN: str = ""
    VAST_COLLECTION_AUTHORIZED: bool = False
    VAST_API_KEY: str = ""
    VAST_HTTP_TIMEOUT: float = 20.0
    VAST_MAX_RESPONSE_BYTES: int = 16 * 1024 * 1024
    VAST_OFFER_LIMIT: int = 500
    VAST_REQUEST_GAP_SECONDS: float = 12.0
    VAST_ON_DEMAND_REFRESH_SECONDS: int = 600
    VAST_BID_REFRESH_SECONDS: int = 300
    VAST_RESERVED_REFRESH_SECONDS: int = 1800

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = CollectorSettings()
