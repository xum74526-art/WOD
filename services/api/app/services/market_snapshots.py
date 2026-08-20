from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from html.parser import HTMLParser
import json
from pathlib import Path
from statistics import mean, median

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import MarketPriceSnapshot


MARKET_SOURCE = "getdeploying"
GETDEPLOYING_SOURCE_URL = "https://getdeploying.com/gpus"
GETDEPLOYING_PRICE_INDEX_URL = "https://getdeploying.com/gpu-price-index"
GETDEPLOYING_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "getdeploying_market_snapshot.json"
GETDEPLOYING_PUBLIC_SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / "data" / "getdeploying_public_index.json"
GETDEPLOYING_BUNDLED_SNAPSHOT_PATH = Path("/opt/kai-bootstrap/getdeploying_public_index.json")


class _ApplicationJsonParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capturing = False
        self._parts: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "script":
            return
        attributes = {key.casefold(): value for key, value in attrs}
        if attributes.get("type", "").casefold() == "application/json":
            self._capturing = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._capturing:
            self.scripts.append("".join(self._parts))
            self._capturing = False
            self._parts = []


def getdeploying_configured() -> bool:
    key = settings.GETDEPLOYING_API_KEY.strip()
    return bool(key and key.casefold() not in {"disabled", "not-configured", "replace-me"})


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        try:
            return datetime.combine(date.fromisoformat(value), datetime.min.time(), tzinfo=timezone.utc)
        except ValueError:
            return None


def _number(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _paginated(client: httpx.Client, path: str, params: dict[str, object]) -> list[dict]:
    page = 1
    result: list[dict] = []
    while page <= 100:
        response = client.get(path, params={**params, "page": page, "page_size": 100})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError(f"GetDeploying {path} response is not paginated JSON")
        result.extend(item for item in payload["data"] if isinstance(item, dict))
        page_count = max(1, int(payload.get("page_count") or 1))
        if page >= page_count:
            return result
        page += 1
    raise ValueError(f"GetDeploying {path} exceeded the pagination safety limit")


def fetch_getdeploying_payload() -> dict:
    if not getdeploying_configured():
        raise RuntimeError("GETDEPLOYING_API_KEY is not configured")
    headers = {
        "Authorization": f"Bearer {settings.GETDEPLOYING_API_KEY.strip()}",
        "Accept": "application/json",
        "User-Agent": "KAI-GPU-Market/1.0",
    }
    timeout = httpx.Timeout(settings.MARKET_SNAPSHOT_HTTP_TIMEOUT_SECONDS)
    with httpx.Client(
        base_url=settings.GETDEPLOYING_API_BASE_URL.rstrip("/"),
        headers=headers,
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        cached = load_getdeploying_payload_cache()
        cached_at = _parse_timestamp((cached or {}).get("reference_data_observed_at"))
        reuse_reference_data = bool(
            cached_at
            and datetime.now(timezone.utc) - cached_at < timedelta(hours=24)
            and isinstance((cached or {}).get("models"), list)
            and isinstance((cached or {}).get("history"), list)
        )
        if reuse_reference_data:
            models = cached["models"]
            history = cached["history"]
            reference_data_observed_at = cached["reference_data_observed_at"]
        else:
            models_response = client.get("/gpus")
            models_response.raise_for_status()
            models_payload = models_response.json()
            if isinstance(models_payload, dict):
                models_payload = models_payload.get("data")
            if not isinstance(models_payload, list):
                raise ValueError("GetDeploying /gpus response is not a model list")
            models = [item for item in models_payload if isinstance(item, dict)]
            history = _paginated(client, "/gpu-price-history", {
                "billing_type": "ON_DEMAND",
                "interval": "daily",
                "date_start": (datetime.now(timezone.utc) - timedelta(days=400)).date().isoformat(),
            })
            reference_data_observed_at = datetime.now(timezone.utc).isoformat()
        offers = _paginated(client, "/gpu-offerings", {
            "billing_type": "ON_DEMAND",
            "availability": "AVAILABLE",
            "sort": "price_per_gpu_hour",
        })

    observed_at = datetime.now(timezone.utc)
    source_times = [
        parsed
        for parsed in (
            _parse_timestamp((item.get("status") or {}).get("last_verified"))
            for item in offers
            if isinstance(item.get("status"), dict)
        )
        if parsed is not None
    ]
    history_times = [parsed for parsed in (_parse_timestamp(item.get("date")) for item in history) if parsed is not None]
    source_updated_at = max(source_times + history_times, default=observed_at)
    return {
        "version": 1,
        "source": MARKET_SOURCE,
        "source_url": GETDEPLOYING_SOURCE_URL,
        "observed_at": observed_at.isoformat(),
        "reference_data_observed_at": reference_data_observed_at,
        "source_updated_at": source_updated_at.isoformat(),
        "models": models,
        "offers": offers,
        "history": history,
    }


def fetch_getdeploying_public_payload() -> dict:
    """Read the public price-index page without requiring the paid API.

    GetDeploying may rate-limit automated requests. Callers should retain the last
    successful snapshot when a refresh fails; the bundled snapshot is the initial
    fallback for a fresh deployment.
    """
    timeout = httpx.Timeout(settings.MARKET_SNAPSHOT_HTTP_TIMEOUT_SECONDS)
    response = httpx.get(
        GETDEPLOYING_PRICE_INDEX_URL,
        timeout=timeout,
        follow_redirects=True,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "User-Agent": "Mozilla/5.0 (compatible; KAI-Market-Snapshot/1.0; +https://kai.com)",
        },
    )
    response.raise_for_status()
    parser = _ApplicationJsonParser()
    parser.feed(response.text)
    page_data: dict | None = None
    for script in parser.scripts:
        try:
            candidate = json.loads(script)
        except ValueError:
            continue
        if isinstance(candidate, dict) and isinstance(candidate.get("cards"), list) and isinstance(candidate.get("index"), dict):
            page_data = candidate
            break
    if page_data is None:
        raise ValueError("GetDeploying public page did not contain GPU price-index data")

    index = page_data["index"]
    models: list[dict] = []
    history: list[dict] = []
    for card in page_data["cards"]:
        if not isinstance(card, dict) or not card.get("in_index"):
            continue
        slug = str(card.get("slug") or "").strip()
        name = str(card.get("name") or slug).strip()
        if not slug:
            continue
        vendor = "AMD" if name.casefold().startswith("amd ") else "NVIDIA"
        models.append({"id": slug, "name": name, "vendor": vendor})
        provider_count = max(0, int(card.get("provider_count") or 0))
        for point in card.get("points") or []:
            if not isinstance(point, dict):
                continue
            price = _number(point.get("value"))
            if point.get("date") and price is not None and price > 0:
                history.append({
                    "gpu_model": slug,
                    "date": point["date"],
                    "median_price": price,
                    "provider_count": provider_count,
                })
    if not models or not history:
        raise ValueError("GetDeploying public page contained no usable indexed GPU history")
    observed_at = datetime.now(timezone.utc)
    latest_date = str(index.get("latest_date") or max(str(item["date"]) for item in history))
    return {
        "version": 1,
        "source": MARKET_SOURCE,
        "source_mode": "public_page_snapshot",
        "source_url": GETDEPLOYING_PRICE_INDEX_URL,
        "observed_at": observed_at.isoformat(),
        "source_updated_at": f"{latest_date}T00:00:00+00:00",
        "models": models,
        "offers": [],
        "history": history,
    }


def _provider_weighted_median(offers: list[dict]) -> float:
    provider_prices: dict[str, list[float]] = defaultdict(list)
    for offer in offers:
        provider = offer.get("provider") or {}
        pricing = offer.get("pricing") or {}
        price = _number(pricing.get("hourly_per_gpu"))
        if price is not None and price > 0:
            provider_prices[str(provider.get("id") or provider.get("name") or "unknown")].append(price)
    medians = [median(prices) for prices in provider_prices.values() if prices]
    return float(median(medians)) if medians else 0.0


def market_summary_from_payload(payload: dict) -> list[dict]:
    offers_by_model: dict[str, list[dict]] = defaultdict(list)
    for offer in payload.get("offers", []):
        configuration = offer.get("configuration") or {}
        pricing = offer.get("pricing") or {}
        status = offer.get("status") or {}
        slug = str(configuration.get("gpu_model") or "").strip()
        price = _number(pricing.get("hourly_per_gpu"))
        if slug and price is not None and price > 0 and status.get("availability") == "AVAILABLE":
            offers_by_model[slug].append(offer)

    history_by_model: dict[str, list[dict]] = defaultdict(list)
    for point in payload.get("history", []):
        slug = str(point.get("gpu_model") or "").strip()
        if not slug or point.get("provider") is not None:
            continue
        history_by_model[slug].append(point)

    summaries = []
    for model in payload.get("models", []):
        slug = str(model.get("id") or "").strip()
        name = str(model.get("name") or slug).strip()
        offers = offers_by_model.get(slug, [])
        history = sorted(history_by_model.get(slug, []), key=lambda item: str(item.get("date") or ""), reverse=True)
        prices = [
            price
            for price in (_number((offer.get("pricing") or {}).get("hourly_per_gpu")) for offer in offers)
            if price is not None and price > 0
        ]
        latest_history = history[0] if history else {}
        historical_median = _number(latest_history.get("provider_median_price")) or _number(latest_history.get("median_price")) or 0.0
        historical_min = _number(latest_history.get("min_price")) or historical_median
        historical_max = _number(latest_history.get("max_price")) or historical_median
        historical_average = _number(latest_history.get("avg_price")) or historical_median
        current_median = _provider_weighted_median(offers) or historical_median
        current_min = min(prices) if prices else historical_min
        current_max = max(prices) if prices else historical_max
        current_average = mean(prices) if prices else historical_average
        representative = min(
            offers,
            key=lambda item: _number((item.get("pricing") or {}).get("hourly_per_gpu")) or float("inf"),
            default={},
        )
        configuration = representative.get("configuration") or {}
        provider = representative.get("provider") or {}
        provider_ids = {
            str((offer.get("provider") or {}).get("id") or (offer.get("provider") or {}).get("name") or "unknown")
            for offer in offers
        }
        price_history = []
        for point in history:
            price = _number(point.get("provider_median_price")) or _number(point.get("median_price"))
            if point.get("date") and price is not None and price > 0:
                price_history.append({"date": point["date"], "median": round(price, 6)})
        if not offers and not price_history:
            continue
        summaries.append({
            "gpu_model": name,
            "gpu_slug": slug,
            "min_price": round(float(current_min), 6),
            "median_price": round(float(current_median), 6),
            "average_price": round(float(current_average), 6),
            "max_price": round(float(current_max), 6),
            "available_gpu_count": sum(max(1, int((offer.get("configuration") or {}).get("gpu_count") or 1)) for offer in offers),
            "offer_count": len(offers),
            "provider_count": len(provider_ids) if offers else int(latest_history.get("provider_count") or 0),
            "has_current_offers": bool(offers),
            "representative_offer_id": representative.get("id"),
            "representative_provider": provider.get("name"),
            "region": provider.get("country"),
            "verification": (representative.get("status") or {}).get("availability"),
            "gpu_count": configuration.get("gpu_count"),
            "cpu_cores": configuration.get("cpu_cores"),
            "ram_gb": configuration.get("system_ram_gb"),
            "disk_gb": configuration.get("disk_storage_gb"),
            "tier": model.get("vendor"),
            "vram_gb": model.get("vram_gb"),
            "official_min_price": round(float(historical_min), 6),
            "official_median_price": round(float(historical_median), 6),
            "official_available": len(offers),
            "history": price_history,
        })
    summaries.sort(key=lambda item: (-int(item["has_current_offers"]), -item["provider_count"], item["gpu_model"]))
    return summaries


def persist_getdeploying_payload_cache(payload: dict) -> None:
    GETDEPLOYING_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = GETDEPLOYING_CACHE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(GETDEPLOYING_CACHE_PATH)


def load_getdeploying_payload_cache() -> dict | None:
    try:
        payload = json.loads(GETDEPLOYING_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if payload.get("version") != 1 or payload.get("source") != MARKET_SOURCE:
        return None
    return payload


def load_getdeploying_public_snapshot() -> dict | None:
    for path in (GETDEPLOYING_PUBLIC_SNAPSHOT_PATH, GETDEPLOYING_BUNDLED_SNAPSHOT_PATH):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if payload.get("version") != 1 or payload.get("source") != MARKET_SOURCE:
            continue
        if not isinstance(payload.get("models"), list) or not isinstance(payload.get("history"), list):
            continue
        return payload
    return None


def refresh_getdeploying_public_snapshot() -> dict:
    payload = fetch_getdeploying_public_payload()
    GETDEPLOYING_PUBLIC_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = GETDEPLOYING_PUBLIC_SNAPSHOT_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(GETDEPLOYING_PUBLIC_SNAPSHOT_PATH)
    return payload


def capture_getdeploying_price_snapshot(
    db: Session,
    payload: dict,
    *,
    observed_at: datetime | None = None,
) -> int:
    captured_at = _utc(observed_at or _parse_timestamp(payload.get("observed_at")) or datetime.now(timezone.utc))
    bucket_hour = captured_at.replace(minute=0, second=0, microsecond=0)
    source_updated_at = _parse_timestamp(payload.get("source_updated_at"))
    captured = 0
    for item in market_summary_from_payload(payload):
        median_price = _number(item.get("median_price"))
        min_price = _number(item.get("min_price"))
        if median_price is None or median_price <= 0:
            continue
        if min_price is None:
            min_price = median_price
        gpu_model = str(item["gpu_model"])[:64]
        row = db.query(MarketPriceSnapshot).filter(
            MarketPriceSnapshot.source == MARKET_SOURCE,
            MarketPriceSnapshot.gpu_model == gpu_model,
            MarketPriceSnapshot.bucket_hour == bucket_hour,
        ).first()
        if row is None:
            row = MarketPriceSnapshot(
                source=MARKET_SOURCE,
                gpu_model=gpu_model,
                bucket_hour=bucket_hour,
                observed_at=captured_at,
                source_updated_at=source_updated_at,
                min_price=Decimal(str(min_price)),
                median_price=Decimal(str(median_price)),
                available=max(0, int(item.get("available_gpu_count") or 0)),
                currency="USD",
                price_unit="gpu_hour",
            )
            db.add(row)
        else:
            row.observed_at = captured_at
            row.source_updated_at = source_updated_at
            row.min_price = Decimal(str(min_price))
            row.median_price = Decimal(str(median_price))
            row.available = max(0, int(item.get("available_gpu_count") or 0))
        captured += 1
    cutoff = captured_at - timedelta(days=settings.MARKET_SNAPSHOT_RETENTION_DAYS)
    db.query(MarketPriceSnapshot).filter(MarketPriceSnapshot.observed_at < cutoff).delete(synchronize_session=False)
    db.commit()
    return captured


def sync_getdeploying_price_snapshot(db: Session) -> int:
    payload = fetch_getdeploying_payload()
    captured = capture_getdeploying_price_snapshot(db, payload)
    persist_getdeploying_payload_cache(payload)
    return captured


def daily_market_candles(db: Session, gpu_model: str, *, days: int = 30) -> list[dict]:
    now = datetime.now(timezone.utc)
    cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=max(1, days) - 1)
    rows = db.query(MarketPriceSnapshot).filter(
        MarketPriceSnapshot.source == MARKET_SOURCE,
        MarketPriceSnapshot.gpu_model == gpu_model,
        MarketPriceSnapshot.observed_at >= cutoff,
    ).order_by(MarketPriceSnapshot.observed_at.asc()).all()
    grouped: dict[str, list[MarketPriceSnapshot]] = defaultdict(list)
    for row in rows:
        grouped[_utc(row.observed_at).date().isoformat()].append(row)
    candles = []
    for day, points in sorted(grouped.items()):
        prices = [float(point.median_price) for point in points]
        candles.append({
            "date": day,
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
            "available": points[-1].available,
            "sample_count": len(points),
        })
    return candles
