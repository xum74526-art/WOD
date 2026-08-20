#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

if [ -x "$repo_root/services/api/.venv/bin/python" ]; then
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$repo_root/services/api" \
    "$repo_root/services/api/.venv/bin/python" -m pytest -q "$repo_root/services/api/tests"
  "$repo_root/services/api/.venv/bin/python" "$repo_root/packages/api-contracts/export_openapi.py"
else
  echo "API dependencies not installed; run the API setup in README.md" >&2
  exit 1
fi

if [ -d "$repo_root/apps/web/node_modules" ]; then
  npm --prefix "$repo_root/apps/web" run type-check
  npm --prefix "$repo_root/apps/web" run build
else
  echo "Web dependencies not installed; run npm ci --prefix apps/web" >&2
  exit 1
fi

if [ -d "$repo_root/apps/mobile/node_modules" ]; then
  npm --prefix "$repo_root/apps/mobile" run type-check
  npm --prefix "$repo_root/apps/mobile" test
  npm --prefix "$repo_root/apps/mobile" run check:ios
  node "$repo_root/packages/api-contracts/check-mobile-api.mjs"
else
  echo "Mobile dependencies not installed; run npm ci --prefix apps/mobile" >&2
  exit 1
fi

(cd "$repo_root/agent" && GOOS=linux GOARCH=amd64 go test ./...)
(cd "$repo_root/agent" && GOOS=windows GOARCH=amd64 go test ./...)

echo "All available project checks passed."
