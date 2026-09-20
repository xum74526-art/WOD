import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.ingestion import MarketOfferBatchIn, MarketOfferBatchResponse
from app.services.market_ingestion import IngestionConflict, ingest_market_offer_batch
from app.utils.response import BizError, success


router = APIRouter(prefix="/internal/v1/ingestion", tags=["internal-ingestion"])
service_bearer = HTTPBearer(auto_error=False)


def require_ingestion_service(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(service_bearer)],
) -> None:
    if not settings.MARKET_INGESTION_ENABLED:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "数据接入服务未启用")
    expected = settings.MARKET_INGESTION_TOKEN.strip()
    if len(expected) < 24:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "数据接入服务安全配置不完整")
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not hmac.compare_digest(credentials.credentials.strip(), expected)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "数据接入凭据无效")


@router.post(
    "/market-offers/batches",
    dependencies=[Depends(require_ingestion_service)],
    response_model=MarketOfferBatchResponse,
)
def ingest_market_offers(payload: MarketOfferBatchIn, db: Session = Depends(get_db)):
    try:
        result = ingest_market_offer_batch(db, payload)
    except IngestionConflict as exc:
        raise BizError("批次编号已被不同数据占用", code=40901, status_code=409) from exc
    return success(result.model_dump(mode="json"))
