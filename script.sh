#!/usr/bin/env bash
set -euo pipefail

# Manual backend runner for local/dev usage.
# This does NOT change or interfere with any preview configuration; it simply
# runs the existing backend_api FastAPI app via uvicorn.
#
# Usage:
#   ./script.sh
#
# Optional environment overrides:
#   PORT=8000 HOST=0.0.0.0 RELOAD=1 ./script.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend_api"

if [[ ! -d "${BACKEND_DIR}" ]]; then
  echo "Error: backend_api directory not found at: ${BACKEND_DIR}" >&2
  exit 1
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-1}"

cd "${BACKEND_DIR}"

# Prefer python -m uvicorn to ensure we use the active interpreter environment.
# The FastAPI app is defined at src/api/main.py as `app`.
UVICORN_CMD=(python -m uvicorn src.api.main:app --host "${HOST}" --port "${PORT}")

if [[ "${RELOAD}" == "1" || "${RELOAD}" == "true" ]]; then
  UVICORN_CMD+=(--reload)
fi

echo "Starting backend_api..."
echo "  cwd: ${BACKEND_DIR}"
echo "  url: http://${HOST}:${PORT}"
echo "  docs: http://${HOST}:${PORT}/docs"
echo "  reload: ${RELOAD}"
echo

exec "${UVICORN_CMD[@]}"
