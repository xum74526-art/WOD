"""Test-only ASGI entrypoint for deterministic browser registration flows."""
from contextlib import asynccontextmanager
import os
import re
from pathlib import Path


if os.environ.get("ZTW_PLAYWRIGHT_E2E") != "1":
    raise RuntimeError("The Playwright API entrypoint is disabled outside explicit E2E runs")

_E2E_CAPTCHA_CODE = os.environ.get("ZTW_E2E_CAPTCHA_CODE", "")
if not re.fullmatch(r"[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{4}", _E2E_CAPTCHA_CODE):
    raise RuntimeError("ZTW_E2E_CAPTCHA_CODE must be four supported CAPTCHA characters")

_DATABASE_URL = os.environ.get("DATABASE_URL", "")
_UPLOAD_ROOT = os.environ.get("UPLOAD_ROOT", "")
if not _DATABASE_URL.startswith("sqlite:///") or "ztw-playwright-e2e-" not in _DATABASE_URL:
    raise RuntimeError("Playwright must use its isolated SQLite database")
if not _UPLOAD_ROOT or "ztw-playwright-e2e-" not in _UPLOAD_ROOT:
    raise RuntimeError("Playwright must use its isolated upload directory")

from app.utils import captcha as captcha_module  # noqa: E402


captcha_module._generate_code = lambda length=4: (_E2E_CAPTCHA_CODE * length)[:length]

from app.main import app  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402


Path(_UPLOAD_ROOT).mkdir(parents=True, exist_ok=True)
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def _isolated_lifespan(_app):
    """E2E requests need routes and storage, never production schedulers or external sync."""
    yield


app.router.lifespan_context = _isolated_lifespan
