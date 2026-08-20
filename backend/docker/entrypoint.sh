#!/bin/sh
set -eu

load_secret() {
  variable="$1"
  eval "secret_file=\${${variable}_FILE:-}"
  if [ -z "$secret_file" ]; then
    return
  fi
  if [ ! -f "$secret_file" ] || [ ! -r "$secret_file" ]; then
    echo "secret file for $variable is missing or unreadable" >&2
    exit 1
  fi
  secret_value="$(cat "$secret_file")"
  if [ -z "$secret_value" ]; then
    echo "secret file for $variable is empty" >&2
    exit 1
  fi
  export "$variable=$secret_value"
}

for variable in \
  SECRET_KEY \
  PAYOUT_ENCRYPTION_KEY \
  KYC_ENCRYPTION_KEY \
  GETDEPLOYING_API_KEY \
  PINGXX_API_KEY \
  PINGXX_MERCHANT_PRIVATE_KEY \
  PINGXX_PUBLIC_KEY \
  SMTP_PASSWORD \
  AGENT_MTLS_PROXY_SECRET
do
  load_secret "$variable"
done

if [ -n "${POSTGRES_PASSWORD_FILE:-}" ]; then
  load_secret POSTGRES_PASSWORD
fi
if [ -n "${REDIS_PASSWORD_FILE:-}" ]; then
  load_secret REDIS_PASSWORD
fi

if [ -z "${DATABASE_URL:-}" ]; then
  : "${POSTGRES_USER:?POSTGRES_USER is required}"
  : "${POSTGRES_DB:?POSTGRES_DB is required}"
  : "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD or POSTGRES_PASSWORD_FILE is required}"
  encoded_postgres_password="$(python -c 'import os, urllib.parse; print(urllib.parse.quote(os.environ["POSTGRES_PASSWORD"], safe=""))')"
  export DATABASE_URL="postgresql+psycopg2://${POSTGRES_USER}:${encoded_postgres_password}@postgres:5432/${POSTGRES_DB}"
fi

if [ -z "${REDIS_URL:-}" ]; then
  : "${REDIS_PASSWORD:?REDIS_PASSWORD or REDIS_PASSWORD_FILE is required}"
  encoded_redis_password="$(python -c 'import os, urllib.parse; print(urllib.parse.quote(os.environ["REDIS_PASSWORD"], safe=""))')"
  export REDIS_URL="redis://:${encoded_redis_password}@redis:6379/0"
fi

exec "$@"
