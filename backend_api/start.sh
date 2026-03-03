#!/usr/bin/env bash
set -euo pipefail

# Start script for Kavia preview/prod-like environments.
#
# Ensures the API listens on the platform-provided $PORT (expected 3001 in preview)
# and binds to $HOST (default 0.0.0.0) so the reverse proxy can reach it.
#
# This script also prefers the project's local venv (./.venv) to avoid situations
# where the platform launches with system Python that lacks dependencies.

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-3001}"
UVICORN_WORKERS="${UVICORN_WORKERS:-1}"

VENV_UVICORN="./.venv/bin/uvicorn"
if [[ -x "${VENV_UVICORN}" ]]; then
  UVICORN_BIN="${VENV_UVICORN}"
else
  UVICORN_BIN="uvicorn"
fi

# Note: do NOT enable --reload by default in preview/proxy environments; it can
# interfere with process supervision. Developers can opt-in via UVICORN_RELOAD=true.
RELOAD_FLAG=""
if [[ "${UVICORN_RELOAD:-false}" == "true" ]]; then
  RELOAD_FLAG="--reload"
fi

exec "${UVICORN_BIN}" src.api.main:app \
  --host "${HOST}" \
  --port "${PORT}" \
  --workers "${UVICORN_WORKERS}" \
  ${RELOAD_FLAG}
