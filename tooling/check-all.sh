#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

if [ -x "$repo_root/services/api/.venv/bin/python" ]; then
  (cd "$repo_root/services/api" && .venv/bin/python -m compileall -q app init_db.py)
  (cd "$repo_root/services/api" && .venv/bin/python -m unittest discover -s tests -p 'test_*.py')
  "$repo_root/services/api/.venv/bin/python" "$repo_root/packages/api-contracts/check_openapi.py"
else
  echo "API dependencies not installed; run the setup in README.md" >&2
  exit 1
fi

if [ -d "$repo_root/apps/web/node_modules" ]; then
  npm --prefix "$repo_root/apps/web" run type-check
  npm --prefix "$repo_root/apps/web" test
  npm --prefix "$repo_root/apps/web" run build
else
  echo "Web dependencies not installed; run npm ci --prefix apps/web" >&2
  exit 1
fi

if [ -d "$repo_root/apps/mobile/node_modules" ]; then
  npm --prefix "$repo_root/apps/mobile" run type-check
  npm --prefix "$repo_root/apps/mobile" test
  node "$repo_root/packages/api-contracts/check-mobile-api.mjs"
  node "$repo_root/packages/api-contracts/check-client-boundaries.mjs"
else
  echo "Mobile dependencies not installed; run npm ci --prefix apps/mobile" >&2
  exit 1
fi

echo "All available project checks passed."
