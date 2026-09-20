from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

import httpx

from collector.config import settings


class IngestionClientError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _validate_url() -> None:
    parsed = urlparse(settings.INGESTION_API_URL)
    local_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not local_http:
        raise IngestionClientError("insecure_ingestion_url")
    if not parsed.path.endswith("/internal/v1/ingestion/market-offers/batches"):
        raise IngestionClientError("ingestion_path_rejected")


def submit_batch(payload: dict[str, Any], *, client: httpx.Client | None = None) -> dict[str, Any]:
    _validate_url()
    token = settings.INGESTION_TOKEN.strip()
    if len(token) < 24:
        raise IngestionClientError("ingestion_token_missing")
    owns_client = client is None
    active_client = client or httpx.Client(timeout=httpx.Timeout(20.0), follow_redirects=False)
    try:
        for attempt in range(3):
            try:
                response = active_client.post(
                    settings.INGESTION_API_URL,
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}",
                        "User-Agent": "KAI-collector/1.0",
                    },
                    json=payload,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == 2:
                    raise IngestionClientError("ingestion_network_error") from exc
                time.sleep(2 ** attempt)
                continue
            if response.status_code >= 500 and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            if response.status_code == 401:
                raise IngestionClientError("ingestion_unauthorized")
            if response.status_code == 409:
                raise IngestionClientError("ingestion_batch_conflict")
            if response.status_code != 200:
                raise IngestionClientError(f"ingestion_http_{response.status_code}")
            try:
                body = response.json()
            except ValueError as exc:
                raise IngestionClientError("ingestion_invalid_json") from exc
            if not isinstance(body, dict) or body.get("code") != 0 or not isinstance(body.get("data"), dict):
                raise IngestionClientError("ingestion_rejected")
            return body["data"]
        raise IngestionClientError("ingestion_retry_exhausted")
    finally:
        if owns_client:
            active_client.close()
