#!/bin/zsh
# Nightly refresh: re-fetch the World Bank sources, rebuild what changed, retrain, evaluate, then ask the running
# backend to load the new data. Run by launchd (deploy/com.procintel.refresh.plist) or by hand.
# Needs the model servers in .env (they wake from idle sleep on the first request) and network access.
set -euo pipefail
cd "${0:A:h}/.."
env_file=.env
[[ -f $env_file ]] || env_file=.env.example
set -a; . ./$env_file; set +a
mkdir -p data/logs
log=data/logs/refresh-$(date +%Y%m%d-%H%M).log
PYTHONPATH=src .venv/bin/python -m procintel.refresh --reload-url "${PROCINTEL_RELOAD_URL:-http://127.0.0.1:8000/admin/reload}" >"$log" 2>&1
echo "refresh finished, log: $log"
