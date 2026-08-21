"""Vast.ai API 客户端：拉取可用 GPU offers。"""
import httpx

from app.core.config import settings


def fetch_bundles() -> list[dict]:
    if not settings.VAST_API_KEY:
        raise RuntimeError("credentials_missing")
    headers = {"Authorization": f"Bearer {settings.VAST_API_KEY}"}
    r = httpx.post(
        f"{settings.VAST_API_BASE_URL.rstrip('/')}/bundles",
        headers=headers,
        json={
            "limit": 500,
            "type": "ondemand",
            "verified": {"eq": True},
            "rentable": {"eq": True},
            "rented": {"eq": False},
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("offers", [])
