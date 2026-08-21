#!/bin/sh
set -eu

require_env() {
    name="$1"
    eval "value=\${$name:-}"
    if [ -z "$value" ]; then
        echo "[WOD] required deployment variable is missing: $name" >&2
        exit 1
    fi
}

for name in SECRET_KEY SENSITIVE_DATA_KEY DATABASE_URL UPLOAD_ROOT; do
    require_env "$name"
done

if [ "$SECRET_KEY" = "wod-dev-secret-key-change-in-production-9f8a7b6c5d4e3f2a1b0c" ]; then
    echo "[WOD] refusing to start with the development SECRET_KEY" >&2
    exit 1
fi

python init_db.py
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
