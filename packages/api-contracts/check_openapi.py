"""Fail CI when the committed OpenAPI snapshot differs from FastAPI."""

import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPOSITORY_ROOT / "services" / "api"
SNAPSHOT = Path(__file__).resolve().with_name("openapi.json")
sys.path.insert(0, str(API_ROOT))

from app.main import app  # noqa: E402


actual = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
expected = app.openapi()
if actual != expected:
    print(
        "OpenAPI snapshot is stale; run `npm run export:openapi` and commit the result.",
        file=sys.stderr,
    )
    raise SystemExit(1)

print("OpenAPI snapshot matches the canonical FastAPI application.")
