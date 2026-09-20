"""Export the canonical FastAPI OpenAPI document for client contract review."""

import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPOSITORY_ROOT / "services" / "api"
OUTPUT = Path(__file__).resolve().with_name("openapi.json")

sys.path.insert(0, str(API_ROOT))

from app.main import app  # noqa: E402


OUTPUT.write_text(
    json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(f"Exported {OUTPUT.relative_to(REPOSITORY_ROOT)}")
