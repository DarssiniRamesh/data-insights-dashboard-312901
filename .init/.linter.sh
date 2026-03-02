#!/bin/bash
set -euo pipefail

cd /home/kavia/workspace/code-generation/data-insights-dashboard-312901/backend_api

# CI robustness:
# The linter may run before dependencies are installed. Ensure we have a venv
# with requirements installed (requirements.txt includes flake8).
if [ ! -f "venv/bin/activate" ]; then
  python -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate

# Ensure dependencies (including flake8) are installed. Use a lightweight check
# to avoid re-installing on every run when CI caches the workspace.
if ! python -c "import flake8" >/dev/null 2>&1; then
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
fi

python -m flake8 .

