from __future__ import annotations

import json
import time
from typing import Any

from collector.adapters.vast import BILLING_MODES, CollectorError, collect_batch, refresh_seconds
from collector.config import settings
from collector.ingestion_client import IngestionClientError, submit_batch


def sync_vast(billing_mode: str) -> dict[str, Any]:
    batch = collect_batch(billing_mode)
    result = submit_batch(batch)
    return {
        "status": "ok",
        "source": "vast",
        "billing_mode": billing_mode,
        **result,
    }


def sync_all() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, billing_mode in enumerate(BILLING_MODES):
        if index:
            time.sleep(max(settings.VAST_REQUEST_GAP_SECONDS, 0.0))
        results.append(sync_vast(billing_mode))
    return results


def run_daemon() -> None:
    now = time.monotonic()
    due = {
        "on-demand": now,
        "bid": now + max(settings.VAST_REQUEST_GAP_SECONDS, 0.0),
        "reserved": now + max(settings.VAST_REQUEST_GAP_SECONDS, 0.0) * 2,
    }
    while True:
        current = time.monotonic()
        billing_mode = min(due, key=due.get)
        if due[billing_mode] > current:
            time.sleep(min(due[billing_mode] - current, 30.0))
            continue
        try:
            print(json.dumps(sync_vast(billing_mode), ensure_ascii=False, default=str), flush=True)
        except (CollectorError, IngestionClientError) as exc:
            print(json.dumps({
                "status": "error", "source": "vast", "billing_mode": billing_mode, "error": exc.code,
            }), flush=True)
        due[billing_mode] = time.monotonic() + max(refresh_seconds(billing_mode), 60)
