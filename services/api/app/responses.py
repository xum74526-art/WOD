from typing import Any


def ok(data: Any = None, meta: dict | None = None) -> dict:
    return {"data": data, "meta": meta or {}}


def fail(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}
