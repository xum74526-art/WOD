import json
from datetime import date, datetime

from redis import Redis
from redis.exceptions import RedisError

from app.config import settings


def redis_client() -> Redis:
    return Redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=1, socket_connect_timeout=1)


def cache_get(key: str):
    try:
        value = redis_client().get(key)
        return json.loads(value) if value else None
    except (RedisError, ValueError):
        return None


def cache_set(key: str, value, ttl: int | None = None) -> bool:
    try:
        redis_client().setex(
            key,
            ttl or settings.NEWS_CACHE_TTL_SECONDS,
            json.dumps(value, ensure_ascii=False, default=lambda item: item.isoformat() if isinstance(item, (date, datetime)) else str(item)),
        )
        return True
    except RedisError:
        return False


def cache_delete_news() -> None:
    try:
        client = redis_client()
        keys = list(client.scan_iter("news:*"))
        if keys:
            client.delete(*keys)
    except RedisError:
        pass
