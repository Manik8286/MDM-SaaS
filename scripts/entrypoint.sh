#!/usr/bin/env bash
# entrypoint.sh — decode base64 secrets, reconstruct DATABASE_URL, optionally migrate, then exec CMD
set -euo pipefail

# ---------------------------------------------------------------------------
# Decode certificate / key secrets from base64 environment variables
# ---------------------------------------------------------------------------

if [ -n "${APNS_CERT_B64:-}" ]; then
    echo "${APNS_CERT_B64}" | base64 -d > /tmp/apns.pem
    export APNS_CERT_PATH=/tmp/apns.pem
    echo "[entrypoint] APNS_CERT_PATH set to /tmp/apns.pem"
fi

if [ -n "${APNS_KEY_B64:-}" ]; then
    echo "${APNS_KEY_B64}" | base64 -d > /tmp/apns.key
    export APNS_KEY_PATH=/tmp/apns.key
    echo "[entrypoint] APNS_KEY_PATH set to /tmp/apns.key"
fi

if [ -n "${MDM_SIGNING_CERT_B64:-}" ]; then
    echo "${MDM_SIGNING_CERT_B64}" | base64 -d > /tmp/mdm_signing.pem
    export MDM_SIGNING_CERT_PATH=/tmp/mdm_signing.pem
    echo "[entrypoint] MDM_SIGNING_CERT_PATH set to /tmp/mdm_signing.pem"
fi

if [ -n "${MDM_SIGNING_KEY_B64:-}" ]; then
    echo "${MDM_SIGNING_KEY_B64}" | base64 -d > /tmp/mdm_signing.key
    export MDM_SIGNING_KEY_PATH=/tmp/mdm_signing.key
    echo "[entrypoint] MDM_SIGNING_KEY_PATH set to /tmp/mdm_signing.key"
fi

# ---------------------------------------------------------------------------
# Reconstruct DATABASE_URL from individual components injected by ECS/Terraform
# DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME must all be present when
# DATABASE_URL is not already set.
# ---------------------------------------------------------------------------

if [ -z "${DATABASE_URL:-}" ]; then
    : "${DB_HOST:?DB_HOST is required when DATABASE_URL is not set}"
    : "${DB_PORT:?DB_PORT is required when DATABASE_URL is not set}"
    : "${DB_USER:?DB_USER is required when DATABASE_URL is not set}"
    : "${DB_PASSWORD:?DB_PASSWORD is required when DATABASE_URL is not set}"
    : "${DB_NAME:?DB_NAME is required when DATABASE_URL is not set}"
    export DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
    echo "[entrypoint] DATABASE_URL constructed from DB_* variables"
fi

# ---------------------------------------------------------------------------
# Optional: run Alembic migrations before starting the application process.
# Set MIGRATE=1 in the task environment to enable this.
# ---------------------------------------------------------------------------

if [ "${MIGRATE:-0}" = "1" ]; then
    echo "[entrypoint] Running Alembic migrations..."
    python -m alembic upgrade head
    echo "[entrypoint] Migrations complete."
fi

# ---------------------------------------------------------------------------
# Hand off to the CMD supplied to the container (uvicorn or worker)
# ---------------------------------------------------------------------------

echo "[entrypoint] Executing: $*"
exec "$@"
