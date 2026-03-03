#!/usr/bin/env bash
set -euo pipefail

# Install-and-run helper for the backend_api container.
#
# This script:
#  - creates a virtual environment (backend_api/.venv) if missing
#  - installs backend_api/requirements.txt into that venv (fixes missing fastapi/uvicorn)
#  - runs the FastAPI app via uvicorn on 0.0.0.0:8000 with --reload (default)
#
# Usage:
#   ./script.sh
#
# Optional environment overrides:
#   HOST=0.0.0.0 PORT=8000 RELOAD=1 ./script.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend_api"
VENV_DIR="${BACKEND_DIR}/.venv"

if [[ ! -d "${BACKEND_DIR}" ]]; then
  echo "Error: backend_api directory not found at: ${BACKEND_DIR}" >&2
  exit 1
fi

REQ_FILE="${BACKEND_DIR}/requirements.txt"
if [[ ! -f "${REQ_FILE}" ]]; then
  echo "Error: requirements.txt not found at: ${REQ_FILE}" >&2
  exit 1
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-3001}"
RELOAD="${RELOAD:-1}"

# Always run from backend_api so uvicorn reload watches the expected directory.
cd "${BACKEND_DIR}"

# Create venv if needed.
if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

# Activate venv (shellcheck is not available in CI; keep it simple/portable).
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

# Upgrade packaging tools and install requirements.
# (non-interactive; consistent output in CI; ensures fastapi/uvicorn are present)
python -m pip install --upgrade pip setuptools wheel >/dev/null
python -m pip install -r "${REQ_FILE}"

# Build uvicorn command.
UVICORN_CMD=(python -m uvicorn src.api.main:app --host "${HOST}" --port "${PORT}")

if [[ "${RELOAD}" == "1" || "${RELOAD}" == "true" ]]; then
  UVICORN_CMD+=(--reload)
fi

# Print the exact startup banner requested.
echo "Starting backend_api..."
echo "  cwd: ${BACKEND_DIR}"
echo "  url: http://${HOST}:${PORT}"
echo "  docs: http://${HOST}:${PORT}/docs"
echo "  reload: ${RELOAD}"
echo

exec "${UVICORN_CMD[@]}"
