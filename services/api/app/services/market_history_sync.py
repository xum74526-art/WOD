"""Scheduled, source-attributed GPU market-history backfill.

The request path never performs network I/O.  A background job first attempts
Vast.ai's official history endpoint and then refreshes a small, date-partitioned
CC BY 4.0 fallback archive.  The two sources remain separate in storage and at
selection time so an external reference series is never presented as an
official Vast observation.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re
from threading import Lock
from typing import Any, Iterable
from urllib.parse import quote

import duckdb
import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.market_price import MarketHistoryPoint, MarketHistorySourceStatus
from app.services.gpu_catalog import (
    canonicalize_gpu,
    memory_variant_from_gb,
    memory_variant_from_text,
    normalize_gpu_variant,
)
from app.services.market_sync import _percentile, _without_outliers, utcnow


OFFICIAL_SOURCE = "vast_official_history"
HF_SOURCE = "hf_gpu_prices"
HF_PROVIDER = "vastai"
HF_PAGE_URL = "https://huggingface.co/datasets/afhubbard/gpu-prices"
OFFICIAL_URL = "https://console.vast.ai/api/v0/metrics/gpu/history/"
MIN_COVERAGE_DAYS = 7
MIN_COVERAGE_SPAN_HOURS = 6 * 24
# Frozen read-only defaults for parsing/selecting already stored legacy data.
# They are deliberately not deployment settings and no downloader is active.
LEGACY_CACHE_ROOT = ""
LEGACY_MAX_FILE_BYTES = 5 * 1024 * 1024
LEGACY_MAX_REFRESH_BYTES = 25 * 1024 * 1024
LEGACY_BACKFILL_DAYS = 10
LEGACY_MIN_EXTERNAL_SAMPLES_PER_DAY = 3
LEGACY_HF_DATASET = "afhubbard/gpu-prices"
LEGACY_HF_LICENSE = "CC BY 4.0"

# Vast's aggregate endpoint identifies the board model but currently omits a
# VRAM field for some rows. Only deterministic vendor configurations are
# mapped here. Ambiguous models stay unmatched rather than being guessed.
OFFICIAL_MODEL_VARIANTS = {
    "RTX4090": "24GB",
    "RTX4090D": "24GB",
    "RTX5070TI": "16GB",
    "RTX5080": "16GB",
    "RTX5090": "32GB",
}

_SYNC_LOCK = Lock()
_DATE_DIR = re.compile(r"^prices/dt=(\d{4}-\d{2}-\d{2})$")
_PARQUET_FILE = re.compile(r"^prices/dt=(\d{4}-\d{2}-\d{2})/(snapshot_[A-Za-z0-9_-]+\.parquet)$")


class HistorySourceFailure(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class HistorySelection:
    points: list[MarketHistoryPoint]
    available: bool
    day_count: int
    span_hours: float
    min_daily_sample_count: int
    change_7d_pct: float | None
    range_low_cny: float | None
    range_high_cny: float | None
    provenance: dict[str, Any] | None


def _cache_root() -> Path:
    configured = LEGACY_CACHE_ROOT
    if configured:
        return Path(configured).expanduser().resolve()
    if settings.UPLOAD_ROOT.strip():
        return (Path(settings.UPLOAD_ROOT).expanduser().resolve() / "market-history-cache")
    return (Path(__file__).resolve().parents[2] / ".cache" / "market-history").resolve()


def _safe_decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not result.is_finite() or result <= 0:
        return None
    return result


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)) and math.isfinite(float(value)):
        epoch = float(value)
        if epoch > 10_000_000_000:
            epoch /= 1000
        parsed = datetime.fromtimestamp(epoch, timezone.utc)
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _median(values: Iterable[Decimal]) -> Decimal:
    ordered = sorted(values)
    if not ordered:
        return Decimal("0")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal("2")


def _fx_rate() -> tuple[Decimal, str, str]:
    raise HistorySourceFailure("history_source_disabled")


def _status(db: Session, source: str) -> MarketHistorySourceStatus:
    row = db.query(MarketHistorySourceStatus).filter(MarketHistorySourceStatus.source == source).first()
    if not row:
        row = MarketHistorySourceStatus(
            source=source,
            upstream_provider="vast",
            refresh_seconds=21600,
        )
        db.add(row)
        db.flush()
    return row


def _due(db: Session, source: str, force: bool) -> bool:
    row = _status(db, source)
    if not row.enabled:
        return False
    if force:
        return True
    if not row.last_attempt_at:
        return True
    return utcnow() - row.last_attempt_at >= timedelta(seconds=max(row.refresh_seconds, 300))


def _point_signature(row: dict[str, Any]) -> str:
    stable = {
        key: (value.isoformat() if isinstance(value, datetime) else str(value) if isinstance(value, Decimal) else value)
        for key, value in row.items()
        if key not in {"collected_at"}
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()


def _point_identity(row: dict[str, Any] | MarketHistoryPoint) -> tuple[str, str, str, str, str, datetime, str]:
    observed_at = _parse_timestamp(
        row.observed_at if isinstance(row, MarketHistoryPoint) else row["observed_at"]
    )
    if observed_at is None:
        raise ValueError("history observation requires a valid timestamp")
    value = (lambda name: getattr(row, name)) if isinstance(row, MarketHistoryPoint) else row.__getitem__
    return (
        value("dataset_source"), value("upstream_provider"), value("gpu_model"),
        value("gpu_variant"), value("billing_mode"), observed_at,
        value("index_method"),
    )


def _deduplicate_point_payloads(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse a refresh batch to one deterministic row per DB identity.

    Some upstream archives can contain an overlapping snapshot file.  Keeping
    the observation with the strongest listing support avoids a whole refresh
    failing on the uniqueness constraint and does not synthesize a price.
    """
    unique: dict[tuple[str, str, str, str, str, datetime, str], dict[str, Any]] = {}
    for original in rows:
        payload = dict(original)
        observed_at = _parse_timestamp(payload.get("observed_at"))
        if observed_at is None:
            continue
        payload["observed_at"] = observed_at
        key = _point_identity(payload)
        current = unique.get(key)
        support = (
            max(int(payload.get("sample_count") or 0), 0),
            max(int(payload.get("available_gpu_count") or 0), 0),
            str(payload.get("source_url") or ""),
        )
        current_support = (
            max(int(current.get("sample_count") or 0), 0),
            max(int(current.get("available_gpu_count") or 0), 0),
            str(current.get("source_url") or ""),
        ) if current else None
        if current is None or support > current_support:
            unique[key] = payload
    return list(unique.values())


def _store_points(db: Session, rows: list[dict[str, Any]]) -> int:
    rows = _deduplicate_point_payloads(rows)
    if not rows:
        return 0
    earliest = min(row["observed_at"] for row in rows)
    sources = {row["dataset_source"] for row in rows}
    existing_rows = db.query(MarketHistoryPoint).filter(
            MarketHistoryPoint.dataset_source.in_(sources),
            MarketHistoryPoint.observed_at >= earliest,
        ).all()
    existing = {_point_identity(point): point for point in existing_rows}
    inserted = 0
    for payload in rows:
        signature = _point_signature(payload)
        key = _point_identity(payload)
        current = existing.get(key)
        if current and current.signature == signature:
            continue
        if current:
            # A corrected parser, revised FX reference or upstream revision can
            # legitimately refresh the same observation. Update it in place so
            # the identity constraint remains idempotent.
            for field, value in payload.items():
                setattr(current, field, value)
            current.signature = signature
        else:
            current = MarketHistoryPoint(**payload, signature=signature)
            try:
                # A savepoint confines a cross-process scheduler race to this
                # observation.  The rest of the import remains commit-able.
                with db.begin_nested():
                    db.add(current)
                    db.flush([current])
            except IntegrityError:
                db.expire_all()
                current = db.query(MarketHistoryPoint).filter(
                    MarketHistoryPoint.dataset_source == key[0],
                    MarketHistoryPoint.upstream_provider == key[1],
                    MarketHistoryPoint.gpu_model == key[2],
                    MarketHistoryPoint.gpu_variant == key[3],
                    MarketHistoryPoint.billing_mode == key[4],
                    MarketHistoryPoint.observed_at == key[5],
                    MarketHistoryPoint.index_method == key[6],
                ).one_or_none()
                if current is None:
                    raise
                for field, value in payload.items():
                    setattr(current, field, value)
                current.signature = signature
            else:
                inserted += 1
            existing[key] = current
    return inserted


def _official_variant(gpu_name: str, details: dict[str, Any]) -> str:
    model = canonicalize_gpu(gpu_name)
    direct = memory_variant_from_text(gpu_name)
    if direct:
        return normalize_gpu_variant(model, direct)
    pricing = details.get("pricing") if isinstance(details.get("pricing"), dict) else {}
    for container in (details, pricing):
        for key in ("gpu_memory_gb", "memory_gb", "vram_gb", "gpu_ram"):
            value = container.get(key)
            try:
                amount = float(value)
            except (TypeError, ValueError):
                continue
            if key == "gpu_ram" and amount > 1024:
                amount /= 1024
            variant = memory_variant_from_gb(amount)
            if variant:
                return normalize_gpu_variant(model, variant)
    # The official aggregate currently omits VRAM for some GPU names. Use only
    # deterministic board specifications; ambiguous families remain unmatched.
    return normalize_gpu_variant(model, OFFICIAL_MODEL_VARIANTS.get(model or "", ""))


def parse_vast_official_history(payload: dict[str, Any], collected_at: datetime, fx: tuple[Decimal, str, str]) -> list[dict[str, Any]]:
    """Parse the documented ``response.gpus[name].pricing`` array structure."""
    points: list[dict[str, Any]] = []
    root = payload.get("response") if isinstance(payload, dict) and isinstance(payload.get("response"), dict) else payload
    gpus = root.get("gpus") if isinstance(root, dict) else None
    if not isinstance(gpus, dict):
        return points
    fx_rate, fx_source, fx_date = fx
    for gpu_name, details in gpus.items():
        if not isinstance(details, dict):
            continue
        model = canonicalize_gpu(str(gpu_name))
        variant = _official_variant(str(gpu_name), details)
        pricing = details.get("pricing")
        if not model or not variant or not isinstance(pricing, dict):
            continue
        timestamps = pricing.get("timestamps") or []
        available = pricing.get("avail_median") or []
        available_low = pricing.get("avail_p10") or []
        available_high = pricing.get("avail_p90") or []
        rented = pricing.get("rented_median") or []
        rented_low = pricing.get("rented_p10") or []
        rented_high = pricing.get("rented_p90") or []
        for index, raw_time in enumerate(timestamps):
            observed_at = _parse_timestamp(raw_time)
            representative = _safe_decimal(available[index] if index < len(available) else None)
            basis = "available_median"
            lows, highs = available_low, available_high
            if representative is None:
                representative = _safe_decimal(rented[index] if index < len(rented) else None)
                basis = "rented_median"
                lows, highs = rented_low, rented_high
            if observed_at is None or representative is None:
                continue
            low = _safe_decimal(lows[index] if index < len(lows) else None) or representative
            high = _safe_decimal(highs[index] if index < len(highs) else None) or representative
            low, high = min(low, representative, high), max(low, representative, high)
            points.append({
                "dataset_source": OFFICIAL_SOURCE,
                "upstream_provider": "vast",
                "gpu_model": model,
                "gpu_variant": variant,
                "billing_mode": "ondemand",
                "currency": "USD",
                "low_price": low.quantize(Decimal("0.000001")),
                "representative_price": representative.quantize(Decimal("0.000001")),
                "high_price": high.quantize(Decimal("0.000001")),
                "low_price_cny": (low * fx_rate).quantize(Decimal("0.000001")),
                "representative_price_cny": (representative * fx_rate).quantize(Decimal("0.000001")),
                "high_price_cny": (high * fx_rate).quantize(Decimal("0.000001")),
                "sample_count": 1,
                "available_gpu_count": 0,
                "fx_rate": fx_rate,
                "fx_source": fx_source,
                "fx_date": fx_date,
                "data_quality": "official",
                "index_method": f"vast_{basis}_per_gpu_hour",
                "source_url": OFFICIAL_URL,
                "license_name": "Vast.ai API terms",
                "dataset_version": None,
                "observed_at": observed_at,
                "collected_at": collected_at,
            })
    return points


def _fetch_vast_official(client: httpx.Client, start: datetime, end: datetime) -> tuple[list[dict[str, Any]], str | None]:
    raise HistorySourceFailure("history_source_disabled")


def _hf_api_dataset(dataset: str) -> str:
    return f"https://huggingface.co/api/datasets/{quote(dataset, safe='/')}"


def _hf_api_tree(dataset: str, path: str) -> str:
    return f"https://huggingface.co/api/datasets/{quote(dataset, safe='/')}/tree/main/{quote(path, safe='/=')}"


def _hf_download_url(dataset: str, revision: str, path: str) -> str:
    return f"https://huggingface.co/datasets/{quote(dataset, safe='/')}/resolve/{quote(revision, safe='')}/{quote(path, safe='/=')}?download=true"


def _valid_parquet(path: Path, expected_size: int | None = None) -> bool:
    if not path.is_file():
        return False
    size = path.stat().st_size
    if size < 8 or (expected_size and size != expected_size):
        return False
    with path.open("rb") as stream:
        start = stream.read(4)
        stream.seek(-4, 2)
        end = stream.read(4)
    return start == b"PAR1" and end == b"PAR1"


def _download_file(client: httpx.Client, url: str, target: Path, expected_size: int) -> int:
    if expected_size <= 0 or expected_size > LEGACY_MAX_FILE_BYTES:
        raise HistorySourceFailure("history_file_size_rejected")
    if _valid_parquet(target, expected_size):
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    written = 0
    try:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            with temporary.open("wb") as stream:
                for chunk in response.iter_bytes(64 * 1024):
                    written += len(chunk)
                    if written > LEGACY_MAX_FILE_BYTES:
                        raise HistorySourceFailure("history_file_size_rejected")
                    stream.write(chunk)
        if written != expected_size or not _valid_parquet(temporary, expected_size):
            raise HistorySourceFailure("history_invalid_parquet")
        temporary.replace(target)
        return written
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def _cached_files() -> list[Path]:
    root = _cache_root()
    files = [path for path in root.glob("dt=*/snapshot_*.parquet") if _valid_parquet(path)]
    return sorted(files)[-max(LEGACY_BACKFILL_DAYS * 2, 14):]


def _cache_manifest() -> dict[str, Any]:
    path = _cache_root() / "manifest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_cache_manifest(revision: str, files: list[Path]) -> None:
    root = _cache_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "manifest.json"
    temporary = root / "manifest.json.part"
    payload = {
        "dataset": LEGACY_HF_DATASET,
        "revision": revision,
        "license": LEGACY_HF_LICENSE,
        "refreshed_at": utcnow().isoformat(timespec="seconds") + "Z",
        "files": [item.relative_to(root).as_posix() for item in files],
    }
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _refresh_hf_cache(client: httpx.Client, end: datetime) -> tuple[list[Path], str, bool]:
    dataset = LEGACY_HF_DATASET
    try:
        repository = client.get(_hf_api_dataset(dataset))
        repository.raise_for_status()
        metadata = repository.json()
        revision = str(metadata.get("sha") or "main")
        tree_response = client.get(_hf_api_tree(dataset, "prices"), params={"recursive": "false", "expand": "false", "limit": 1000})
        tree_response.raise_for_status()
        dates: list[tuple[date, str]] = []
        for item in tree_response.json():
            match = _DATE_DIR.fullmatch(str(item.get("path") or ""))
            if not match:
                continue
            value = date.fromisoformat(match.group(1))
            if value <= end.date():
                dates.append((value, item["path"]))
        dates.sort()
        selected = dates[-max(LEGACY_BACKFILL_DAYS, 7):]
        if len(selected) < MIN_COVERAGE_DAYS:
            raise HistorySourceFailure("history_partition_coverage_insufficient")

        entries: list[dict[str, Any]] = []
        for _, directory in selected:
            response = client.get(_hf_api_tree(dataset, directory), params={"recursive": "false", "expand": "false"})
            response.raise_for_status()
            for item in response.json():
                match = _PARQUET_FILE.fullmatch(str(item.get("path") or ""))
                size = int(item.get("size") or 0)
                if match and 0 < size <= LEGACY_MAX_FILE_BYTES:
                    entries.append({"path": item["path"], "date": match.group(1), "filename": match.group(2), "size": size})
        if not entries:
            raise HistorySourceFailure("history_no_parquet_files")
        expected_new = sum(entry["size"] for entry in entries)
        if expected_new > LEGACY_MAX_REFRESH_BYTES:
            raise HistorySourceFailure("history_refresh_size_rejected")

        files: list[Path] = []
        downloaded = 0
        root = _cache_root()
        for entry in entries:
            target = (root / f"dt={entry['date']}" / entry["filename"]).resolve()
            if root not in target.parents:
                raise HistorySourceFailure("history_cache_path_rejected")
            downloaded += _download_file(
                client,
                _hf_download_url(dataset, revision, entry["path"]),
                target,
                entry["size"],
            )
            if downloaded > LEGACY_MAX_REFRESH_BYTES:
                raise HistorySourceFailure("history_refresh_size_rejected")
            files.append(target)
        files = sorted(files)
        _write_cache_manifest(revision, files)
        return files, revision, False
    except (httpx.HTTPError, ValueError, KeyError, HistorySourceFailure) as exc:
        cached = _cached_files()
        if cached:
            revision = str(_cache_manifest().get("revision") or "cached_unknown")
            return cached, revision, True
        if isinstance(exc, HistorySourceFailure):
            raise
        if isinstance(exc, httpx.TimeoutException):
            raise HistorySourceFailure("history_upstream_timeout") from exc
        raise HistorySourceFailure("history_upstream_error") from exc


def _normalized_archive_provider(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return {
        "vastai": "vast",
        "lambdalabs": "lambda",
    }.get(normalized, normalized)


def parse_hf_parquet(
    files: list[Path],
    revision: str,
    collected_at: datetime,
    fx: tuple[Decimal, str, str],
    provider_filter: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Read qualifying, provider-separated on-demand rows from the archive.

    ``provider_filter`` is primarily useful for focused tests.  Production
    imports every provider present in the licensed archive so an exact
    model/VRAM pair can still have an attributed market-reference curve when
    Vast has no historical observations.  Providers are never blended into a
    single time series.
    """
    if not files:
        return []
    connection = duckdb.connect(database=":memory:")
    try:
        raw = connection.execute(
            """
            SELECT filename, lower(provider), timestamp, gpu_type, gpu_count, gpu_memory_gb,
                   price_per_hour / gpu_count AS per_gpu_hour
              FROM read_parquet(?, filename = true)
             WHERE lower(quality) = 'ok'
               AND available IS TRUE
               AND is_spot IS FALSE
               AND gpu_count > 0
               AND gpu_memory_gb > 0
               AND price_per_hour > 0
             ORDER BY timestamp ASC
            """,
            [[str(path) for path in files]],
        ).fetchall()
    finally:
        connection.close()

    normalized_filter = {
        _normalized_archive_provider(provider) for provider in provider_filter
    } if provider_filter is not None else None
    grouped: dict[tuple[str, str, datetime, str, str], list[tuple[Decimal, int]]] = defaultdict(list)
    for filename, raw_provider, raw_time, gpu_type, gpu_count, memory_gb, raw_price in raw:
        provider = _normalized_archive_provider(raw_provider)
        if not provider or (normalized_filter is not None and provider not in normalized_filter):
            continue
        model = canonicalize_gpu(str(gpu_type))
        variant = normalize_gpu_variant(model, memory_gb)
        observed_at = _parse_timestamp(raw_time)
        price = _safe_decimal(raw_price)
        if not model or not variant or observed_at is None or price is None:
            continue
        grouped[(str(filename), provider, observed_at, model, variant)].append((price, max(int(gpu_count), 1)))

    fx_rate, fx_source, fx_date = fx
    dataset = LEGACY_HF_DATASET
    points: list[dict[str, Any]] = []
    cache = _cache_root()
    for (filename, provider, observed_at, model, variant), observations in grouped.items():
        prices = _without_outliers([item[0] for item in observations])
        if not prices:
            continue
        accepted_prices = set(prices)
        # IQR inclusion is value-based, so equal prices are either all accepted
        # or all rejected. Count each original observation exactly once.
        accepted_gpu_count = sum(count for price, count in observations if price in accepted_prices)
        low = min(prices)
        representative = _percentile(prices, Decimal("0.5"))
        high = max(prices)
        try:
            relative = Path(filename).resolve().relative_to(cache).as_posix()
            artifact_path = f"prices/{relative}"
            source_url = _hf_download_url(
                dataset,
                revision if revision not in {"cached", "cached_unknown"} else "main",
                artifact_path,
            ).split("?", 1)[0]
        except ValueError:
            source_url = HF_PAGE_URL
        points.append({
            "dataset_source": HF_SOURCE,
            "upstream_provider": provider,
            "gpu_model": model,
            "gpu_variant": variant,
            "billing_mode": "ondemand",
            "currency": "USD",
            "low_price": low.quantize(Decimal("0.000001")),
            "representative_price": representative.quantize(Decimal("0.000001")),
            "high_price": high.quantize(Decimal("0.000001")),
            "low_price_cny": (low * fx_rate).quantize(Decimal("0.000001")),
            "representative_price_cny": (representative * fx_rate).quantize(Decimal("0.000001")),
            "high_price_cny": (high * fx_rate).quantize(Decimal("0.000001")),
            "sample_count": len(prices),
            "available_gpu_count": accepted_gpu_count,
            "fx_rate": fx_rate,
            "fx_source": fx_source,
            "fx_date": fx_date,
            "data_quality": "external_reference",
            # Keep Vast's original method identifier so a wider provider import
            # upgrades the existing cache row instead of duplicating it. Other
            # providers carry their name because their series must remain
            # independently attributable and must never be blended together.
            "index_method": (
                "cross_listing_iqr_median_per_gpu_hour"
                if provider == "vast"
                else f"{provider}_cross_listing_iqr_median_per_gpu_hour"
            ),
            "source_url": source_url,
            "license_name": LEGACY_HF_LICENSE,
            "dataset_version": revision,
            "observed_at": observed_at,
            "collected_at": collected_at,
        })
    return points


def _set_success(db: Session, source: str, rows: list[dict[str, Any]], version: str | None, cached: bool = False) -> None:
    state = _status(db, source)
    state.status = "cached" if cached else "ok"
    state.sample_count = len(rows)
    state.last_success_at = utcnow()
    state.last_error = None
    state.dataset_version = version
    if source == HF_SOURCE:
        state.upstream_provider = "multi_provider"
        state.license_name = LEGACY_HF_LICENSE
        state.source_url = HF_PAGE_URL
    else:
        state.upstream_provider = "vast"
        state.license_name = "Vast.ai API terms"
        state.source_url = OFFICIAL_URL


def _set_error(db: Session, source: str, code: str) -> None:
    state = _status(db, source)
    state.status = "error"
    state.last_error = code


def sync_market_history(force: bool = False) -> list[dict[str, Any]]:
    """Retained API surface for old operators; KAI-only mode never downloads it."""
    return [{"status": "disabled", "reason": "kai_only_market"}]


def _provenance(point: MarketHistoryPoint, components: list[str] | None = None) -> dict[str, Any]:
    return {
        "kind": point.data_quality,
        "dataset_source": point.dataset_source,
        "upstream_provider": point.upstream_provider,
        "license": point.license_name,
        "source_url": point.source_url,
        "dataset_version": point.dataset_version,
        "collected_at": point.collected_at.isoformat(timespec="seconds") + "Z" if point.collected_at else None,
        "index_method": point.index_method,
        "components": components or [point.dataset_source],
    }


def _selection(points: list[MarketHistoryPoint]) -> HistorySelection:
    ordered = sorted(
        [point for point in points if point.representative_price_cny is not None and point.representative_price_cny > 0],
        key=lambda point: point.observed_at,
    )
    by_day: dict[date, list[Decimal]] = defaultdict(list)
    daily_sample_counts: dict[date, list[int]] = defaultdict(list)
    for point in ordered:
        by_day[point.observed_at.date()].append(Decimal(point.representative_price_cny))
        daily_sample_counts[point.observed_at.date()].append(max(int(point.sample_count), 0))
    daily = sorted((day, _median(values)) for day, values in by_day.items())
    span = 0.0
    if ordered:
        span = max((ordered[-1].observed_at - ordered[0].observed_at).total_seconds() / 3600, 0.0)
    min_daily_samples = min((max(values) for values in daily_sample_counts.values()), default=0)
    quality_kind = ordered[-1].data_quality if ordered else ""
    complete_daily_coverage = len(daily) >= MIN_COVERAGE_DAYS
    strong_listing_support = min_daily_samples >= max(
        LEGACY_MIN_EXTERNAL_SAMPLES_PER_DAY,
        1,
    )
    # A seven-day endpoint change needs observations on both ends of a window,
    # not seven invented daily values. Sparse-but-real dates remain chartable
    # and are explicitly downgraded in provenance instead of being discarded.
    available = (
        len(daily) >= 2
        and span >= MIN_COVERAGE_SPAN_HOURS
    )
    change = None
    low = None
    high = None
    if available:
        first, last = daily[0][1], daily[-1][1]
        if first > 0:
            change = round(float((last / first - Decimal("1")) * Decimal("100")), 2)
        low = float(min(value for _, value in daily))
        high = float(max(value for _, value in daily))
    provenance = _provenance(ordered[-1]) if ordered else None
    if provenance is not None:
        provenance.update({
            "coverage_quality": (
                "verified"
                if complete_daily_coverage and (quality_kind == "official" or strong_listing_support)
                else "limited_sample"
            ),
            "coverage_day_count": len(daily),
            "coverage_span_hours": round(span, 1),
            "minimum_daily_listing_support": min_daily_samples,
            "has_daily_gaps": len(daily) < MIN_COVERAGE_DAYS,
        })
    return HistorySelection(
        points=ordered,
        available=available,
        day_count=len(daily),
        span_hours=round(span, 1),
        min_daily_sample_count=min_daily_samples,
        change_7d_pct=change,
        range_low_cny=low,
        range_high_cny=high,
        provenance=provenance,
    )


def _preferred_selection(grouped: dict[object, list[MarketHistoryPoint]]) -> HistorySelection | None:
    """Choose one attributed series without mixing archives.

    Keeping this decision in one helper lets list endpoints load all requested
    model identities with a single SQL query.  The previous per-model helper
    issued one query for every row in the market ranking, which became an N+1
    request hotspot as the GPU catalogue grew.
    """
    if not grouped:
        return None
    def source_priority(selection: HistorySelection) -> tuple[int, str]:
        if not selection.points:
            return (99, "")
        point = selection.points[0]
        if point.dataset_source == OFFICIAL_SOURCE and point.upstream_provider == "vast":
            return (0, "vast")
        if point.dataset_source == HF_SOURCE and point.upstream_provider == "vast":
            return (1, "vast")
        # A licensed, exact model/VRAM, single-provider series is a fallback
        # market reference. It never masquerades as Vast or AutoDL history.
        return (10, point.upstream_provider)

    candidates = [_selection(points) for points in grouped.values()]
    def selection_priority(item: HistorySelection) -> tuple[Any, ...]:
        source_rank, provider = source_priority(item)
        if item.available:
            # Official/Vast-attributed full-window data wins among usable
            # histories. Coverage then breaks ties without combining sources.
            return (0, source_rank, provider, -item.day_count, -item.span_hours)
        # For incomplete histories, two real observations are more useful than
        # a preferred provider's lone observation. Provider priority is only a
        # tie-breaker after real temporal coverage.
        return (1, -item.day_count, -item.span_hours, source_rank, provider)

    candidates.sort(key=selection_priority)
    return candidates[0]


def select_market_history_bulk(
    db: Session,
    identities: Iterable[tuple[str, str]],
    since: datetime,
    until: datetime | None = None,
    billing_mode: str = "ondemand",
) -> dict[tuple[str, str], HistorySelection]:
    """Select real history for many exact GPU identities in one DB scan."""
    requested = {(str(model), str(variant)) for model, variant in identities}
    if not requested:
        return {}
    canonical_requests: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for original in requested:
        model = canonicalize_gpu(original[0]) or original[0]
        variant = normalize_gpu_variant(model, original[1])
        canonical_requests[(model, variant)].add(original)
    models = {model for model, _ in canonical_requests}
    variants = {variant for _, variant in canonical_requests}
    # H200's 140/141 GB labels describe the same physical SKU. Include both
    # stored spellings during the transition, then normalize before grouping.
    if any(model == "H200" and variant == "141GB" for model, variant in canonical_requests):
        variants.add("140GB")
    query = db.query(MarketHistoryPoint).filter(
        MarketHistoryPoint.billing_mode == billing_mode,
        MarketHistoryPoint.gpu_model.in_(models),
        MarketHistoryPoint.gpu_variant.in_(variants),
        MarketHistoryPoint.observed_at >= since,
        MarketHistoryPoint.representative_price_cny.isnot(None),
    )
    if until is not None:
        query = query.filter(MarketHistoryPoint.observed_at <= until)
    grouped: dict[tuple[str, str], dict[tuple[str, str], list[MarketHistoryPoint]]] = defaultdict(lambda: defaultdict(list))
    for point in query.order_by(
        MarketHistoryPoint.gpu_model.asc(),
        MarketHistoryPoint.gpu_variant.asc(),
        MarketHistoryPoint.dataset_source.asc(),
        MarketHistoryPoint.observed_at.asc(),
    ).all():
        point_model = canonicalize_gpu(point.gpu_model) or point.gpu_model
        identity = (point_model, normalize_gpu_variant(point_model, point.gpu_variant))
        if identity in canonical_requests:
            grouped[identity][(point.dataset_source, point.upstream_provider)].append(point)
    selected: dict[tuple[str, str], HistorySelection] = {}
    for identity, source_groups in grouped.items():
        candidate = _preferred_selection(source_groups)
        if candidate is not None:
            for original in canonical_requests[identity]:
                selected[original] = candidate
    return selected


def select_market_history(
    db: Session,
    model: str,
    variant: str,
    since: datetime,
    until: datetime | None = None,
    billing_mode: str = "ondemand",
) -> HistorySelection | None:
    return select_market_history_bulk(
        db,
        {(model, variant)},
        since,
        until,
        billing_mode,
    ).get((model, variant))


def history_source_status(db: Session) -> list[dict[str, Any]]:
    return [{
        "source": row.source,
        "upstream_provider": row.upstream_provider,
        "status": row.status,
        "refresh_seconds": row.refresh_seconds,
        "sample_count": row.sample_count,
        "last_attempt_at": row.last_attempt_at.isoformat(timespec="seconds") + "Z" if row.last_attempt_at else None,
        "last_success_at": row.last_success_at.isoformat(timespec="seconds") + "Z" if row.last_success_at else None,
        "error_code": row.last_error,
        "required_api_permission": "machine_read" if row.source == OFFICIAL_SOURCE else None,
        "dataset_version": row.dataset_version,
        "license": row.license_name,
        "source_url": row.source_url,
    } for row in db.query(MarketHistorySourceStatus).filter(
        MarketHistorySourceStatus.enabled.is_(True)
    ).order_by(MarketHistorySourceStatus.source.asc()).all()]
