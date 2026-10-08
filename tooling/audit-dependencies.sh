#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

# Registry audit alone cannot validate the repository-maintained braces fork.
node "$repo_root/tooling/test-braces-security.mjs"

"$repo_root/services/api/.venv/bin/python" -m pip_audit -r "$repo_root/services/api/requirements.txt"
"$repo_root/services/api/.venv/bin/python" -m pip_audit -r "$repo_root/services/collector/requirements.txt"
npm --prefix "$repo_root/apps/web" audit --audit-level=high --registry=https://registry.npmjs.org
npm --prefix "$repo_root/apps/ios" audit --audit-level=high --registry=https://registry.npmjs.org
npm --prefix "$repo_root/apps/android" audit --audit-level=high --registry=https://registry.npmjs.org

echo "No known dependency vulnerabilities found."
