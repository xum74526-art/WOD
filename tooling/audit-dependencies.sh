#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

"$repo_root/services/api/.venv/bin/python" -m pip_audit -r "$repo_root/services/api/requirements.txt"
npm --prefix "$repo_root/apps/web" audit --audit-level=high
npm --prefix "$repo_root/apps/mobile" audit --audit-level=high

echo "No known dependency vulnerabilities found."
