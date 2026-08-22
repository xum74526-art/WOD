from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import re
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from collector.config import settings
from collector.normalizers.gpu import canonicalize_gpu, normalize_gpu_variant


SOURCE_URL = "https://console.vast.ai/api/v0/bundles/"
BILLING_MODES = ("on-demand", "bid", "reserved")


class CollectorError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result[:limit] if result else None


def _fallback_model(gpu_name: str) -> str | None:
    result = re.sub(r"[^A-Z0-9]+", "", gpu_name.upper())[:64]
    return result or None


def _header_int(response: httpx.Response, name: str) -> int | None:
    raw = response.headers.get(name)
    try:
        return int(float(raw)) if raw is not None else None
    except (TypeError, ValueError):
        return None


def fetch_raw_offers(
    billing_mode: str,
    *,
    client: httpx.Client | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not settings.VAST_COLLECTION_AUTHORIZED:
        raise CollectorError("authorization_not_confirmed")
    if billing_mode not in BILLING_MODES:
        raise CollectorError("billing_mode_invalid")
    parsed = urlparse(SOURCE_URL)
    if parsed.scheme != "https" or parsed.hostname != "console.vast.ai" or parsed.path != "/api/v0/bundles/":
        raise CollectorError("source_url_rejected")

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "KAI-authorized-market-collector/2.0",
    }
    if settings.VAST_API_KEY:
        headers["Authorization"] = f"Bearer {settings.VAST_API_KEY}"
    request_body = {
        "limit": max(1, min(settings.VAST_OFFER_LIMIT, 5000)),
        "type": billing_mode,
        "verified": {"eq": True},
        "rentable": {"eq": True},
        "rented": {"eq": False},
    }

    owns_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(settings.VAST_HTTP_TIMEOUT),
        follow_redirects=False,
    )
    try:
        with active_client.stream("POST", SOURCE_URL, headers=headers, json=request_body) as response:
            metadata = {
                "limit": _header_int(response, "x-ratelimit-limit"),
                "remaining": _header_int(response, "x-ratelimit-remaining"),
            }
            reset_epoch = _header_int(response, "x-ratelimit-reset")
            metadata["reset_at"] = (
                datetime.fromtimestamp(reset_epoch, timezone.utc).isoformat() if reset_epoch else None
            )
            if response.status_code == 429:
                raise CollectorError("rate_limited")
            if response.status_code in {401, 403}:
                raise CollectorError("access_denied")
            if response.is_redirect:
                raise CollectorError("redirect_rejected")
            if response.status_code != 200:
                raise CollectorError(f"upstream_http_{response.status_code}")
            declared = _integer(response.headers.get("content-length"))
            if declared and declared > settings.VAST_MAX_RESPONSE_BYTES:
                raise CollectorError("response_too_large")
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes(64 * 1024):
                size += len(chunk)
                if size > settings.VAST_MAX_RESPONSE_BYTES:
                    raise CollectorError("response_too_large")
                chunks.append(chunk)
    except httpx.TimeoutException as exc:
        raise CollectorError("upstream_timeout") from exc
    except httpx.HTTPError as exc:
        raise CollectorError("upstream_network_error") from exc
    finally:
        if owns_client:
            active_client.close()

    try:
        payload = json.loads(b"".join(chunks))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CollectorError("invalid_json") from exc
    offers = payload.get("offers") if isinstance(payload, dict) else None
    if not isinstance(offers, list):
        raise CollectorError("invalid_payload")
    valid = [item for item in offers if isinstance(item, dict)]
    if len(valid) > request_body["limit"]:
        raise CollectorError("offer_limit_exceeded")
    return valid, metadata


def normalize_offer(raw: dict[str, Any]) -> dict[str, Any] | None:
    external_id = _integer(raw.get("id"))
    gpu_name = _text(raw.get("gpu_name"), 96)
    gpu_count = max(_integer(raw.get("num_gpus")) or 0, 0)
    compute_total = _number(raw.get("dph_base"))
    total_price = _number(raw.get("dph_total"))
    if not external_id or not gpu_name or gpu_count < 1 or compute_total is None or total_price is None:
        return None
    if compute_total < 0 or total_price < 0:
        return None
    model = canonicalize_gpu(gpu_name) or _fallback_model(gpu_name)
    if not model:
        return None
    gpu_ram_mb = _integer(raw.get("gpu_ram"))
    return {
        "external_id": external_id,
        "gpu_name": gpu_name,
        "gpu_model": model,
        "gpu_variant": normalize_gpu_variant(model, gpu_ram_mb),
        "gpu_count": gpu_count,
        "gpu_ram_mb": gpu_ram_mb,
        "gpu_total_ram_mb": _integer(raw.get("gpu_total_ram")),
        "compute_capability": _integer(raw.get("compute_cap")),
        "cuda_version": _number(raw.get("cuda_max_good")),
        "gpu_memory_bandwidth": _number(raw.get("gpu_mem_bw")),
        "nvlink_bandwidth": _number(raw.get("bw_nvlink")),
        "total_flops": _number(raw.get("total_flops")),
        "cpu_name": _text(raw.get("cpu_name"), 160),
        "cpu_arch": _text(raw.get("cpu_arch"), 32),
        "cpu_cores": _integer(raw.get("cpu_cores")),
        "cpu_ram_mb": _integer(raw.get("cpu_ram")),
        "disk_space_gb": _number(raw.get("disk_space")),
        "disk_bandwidth_mbps": _number(raw.get("disk_bw")),
        "internet_down_mbps": _number(raw.get("inet_down")),
        "internet_up_mbps": _number(raw.get("inet_up")),
        "region": _text(raw.get("geolocation"), 160),
        "hosting_type": _text(raw.get("hosting_type"), 48),
        "verification": _text(raw.get("verification"), 48),
        "reliability": _number(raw.get("reliability")),
        "duration_days": _number(raw.get("duration")),
        "currency": "USD",
        "compute_price_hourly": compute_total,
        "total_price_hourly": total_price,
        "per_gpu_compute_price_hourly": compute_total / gpu_count,
        "per_gpu_total_price_hourly": total_price / gpu_count,
        "minimum_bid_hourly": _number(raw.get("min_bid")),
        "storage_price_gb_month": _number(raw.get("storage_cost")),
        "internet_down_price_tb": _number(raw.get("inet_down_cost")),
        "internet_up_price_tb": _number(raw.get("inet_up_cost")),
        "discount_rate": _number(raw.get("discount_rate")),
        "rentable": bool(raw.get("rentable", True)),
        "rented": bool(raw.get("rented", False)),
    }


def refresh_seconds(billing_mode: str) -> int:
    return {
        "on-demand": settings.VAST_ON_DEMAND_REFRESH_SECONDS,
        "bid": settings.VAST_BID_REFRESH_SECONDS,
        "reserved": settings.VAST_RESERVED_REFRESH_SECONDS,
    }[billing_mode]


def collect_batch(billing_mode: str) -> dict[str, Any]:
    observed_at = datetime.now(timezone.utc)
    raw_offers, metadata = fetch_raw_offers(billing_mode)
    records = [record for raw in raw_offers if (record := normalize_offer(raw))]
    if not records:
        raise CollectorError("no_valid_offers")
    batch_id = f"vast:{billing_mode}:{observed_at.strftime('%Y%m%dT%H%M%SZ')}:{uuid4().hex[:8]}"
    return {
        "schema_version": "1.0",
        "source": "vast",
        "dataset": "gpu_offers",
        "billing_mode": billing_mode,
        "batch_id": batch_id,
        # Vast search returns a changing market sample, not a proven full export.
        "sync_mode": "incremental",
        "observed_at": observed_at.isoformat(),
        "refresh_seconds": refresh_seconds(billing_mode),
        "upstream_rate_limit": metadata.get("limit"),
        "upstream_rate_limit_remaining": metadata.get("remaining"),
        "upstream_rate_limit_reset_at": metadata.get("reset_at"),
        "records": records,
    }
