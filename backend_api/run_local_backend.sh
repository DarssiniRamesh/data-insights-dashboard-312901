#!/usr/bin/env bash
set -euo pipefail

# Simple local dev runner for the backend_api FastAPI service.
#
# What it does:
#  1) Creates/uses a local Python virtualenv in backend_api/.venv
#  2) Installs Python dependencies from requirements.txt
#  3) Starts the FastAPI server with uvicorn (auto-reload enabled)
#
# Usage:
#  cd data-insights-dashboard-312901/backend_api
#  ./run_local_backend.sh
#
# Optional environment variables:
#  PORT (default: 8000)
#  HOST (default: 127.0.0.1)
#  LOG_LEVEL (default: INFO)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

VENV_DIR=".venv"

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "[backend_api] Creating virtualenv at ${VENV_DIR} ..."
  python3 -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

echo "[backend_api] Upgrading pip ..."
python -m pip install --upgrade pip

echo "[backend_api] Installing dependencies (requirements.txt) ..."
pip install -r requirements.txt

echo "[backend_api] Starting server on http://${HOST}:${PORT} (reload enabled) ..."
echo "[backend_api] OpenAPI docs: http://${HOST}:${PORT}/docs"
echo "[backend_api] Readiness:   http://${HOST}:${PORT}/ready"
echo "[backend_api] Liveness:    http://${HOST}:${PORT}/health"

# Ensure imports work (tests configure pythonpath=src; we mimic that here)
export PYTHONPATH="${SCRIPT_DIR}/src:${PYTHONPATH:-}"
export LOG_LEVEL="${LOG_LEVEL}"

exec uvicorn api.main:app --host "${HOST}" --port "${PORT}" --reload
