#!/bin/bash
# Keeps the public demo up: the backend, the three model servers, the tunnel, and the Vercel site's pointer to the tunnel.
#   scripts/demo-watchdog.sh          loop forever (what launchd runs)
#   scripts/demo-watchdog.sh --once   one pass, then exit
# What it checks is what a visitor goes through: the site's proxy to the backend (expects 401 signed out, 200 signed in).
# It never starts anything with sign-in off, and redeploys at most once every MIN_REPOINT_GAP seconds.
# Settings are environment variables with the defaults below; nothing here is a secret.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="${PROCINTEL_RUN_DIR:-$HOME/.procintel-demo}"; mkdir -p "$RUN"
SITE="${PROCINTEL_SITE:-https://procintel-demo.vercel.app}"
INTERVAL="${WATCHDOG_INTERVAL:-45}"
MIN_REPOINT_GAP="${MIN_REPOINT_GAP:-600}"
MODELS="${PROCINTEL_MODEL_DIR:-$HOME/Library/Application Support/omnynet/models}"
LAYA="${PROCINTEL_LAYA_MODEL:-$HOME/models/laya/Laya-Q8_0.gguf}"
LOG="$RUN/watchdog.log"

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }
code() { curl -s -m "${2:-8}" -o /dev/null -w '%{http_code}' "$1" 2>/dev/null; }

backend_up() { [ "$(code http://127.0.0.1:8000/health)" = 200 ]; }
model_up()   { [ "$(code "http://127.0.0.1:$1/health")" = 200 ]; }
site_ok()    { case "$(code "$SITE/api/backend/auth/me" 25)" in 200|401) return 0;; *) return 1;; esac; }

start_backend() {
  log "starting the backend"
  ( cd "$ROOT" && set -a && . ./.env.example && [ -f .env ] && . ./.env; set +a
    PYTHONPATH=src nohup .venv/bin/uvicorn procintel.api.app:app --host 127.0.0.1 --port 8000 >> "$RUN/api.log" 2>&1 & )
}
start_model() {   # port, then llama-server arguments
  local port="$1"; shift
  log "starting the model server on :$port"
  nohup llama-server "$@" --host 127.0.0.1 --port "$port" --sleep-idle-seconds 300 >> "$RUN/model-$port.log" 2>&1 &
}
start_models() {
  model_up 8080 || start_model 8080 -m "$MODELS/underdog-saluki-27b-1.0-iq2.gguf" --alias saluki-27b -c 8192 -np 1
  model_up 8081 || start_model 8081 -m "$MODELS/embeddinggemma-2-q8_0.gguf" --embedding --alias embeddinggemma-2 -c 8192 -b 2048 -ub 2048 -np 4
  model_up 8082 || start_model 8082 -m "$LAYA" --alias laya -c 8192 -b 2048 -ub 2048 -np 1
}

# New tunnel, new address: point the site at it and redeploy. Quick tunnels change address on every start.
repoint() {
  local now last gap; now=$(date +%s); last=$(cat "$RUN/last-repoint" 2>/dev/null || echo 0); gap=$((now - last))
  if [ "$gap" -lt "$MIN_REPOINT_GAP" ]; then log "site check failing but the last repair was ${gap}s ago (< ${MIN_REPOINT_GAP}s): waiting"; return; fi
  echo "$now" > "$RUN/last-repoint"
  log "repairing: restarting the tunnel"
  pkill -f "cloudflared tunnel"; sleep 1
  nohup cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8000 > "$RUN/tunnel.log" 2>&1 &
  local url="" i
  for i in $(seq 1 30); do
    url=$(/usr/bin/grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$RUN/tunnel.log" | head -1)
    [ -n "$url" ] && /usr/bin/grep -q "Registered tunnel connection" "$RUN/tunnel.log" && break; sleep 2
  done
  [ -n "$url" ] || { log "no tunnel address after 60s"; return; }
  local host="${url#https://}" ip c=""
  for i in $(seq 1 20); do   # this Mac's resolver can lag behind a new name; Cloudflare's does not
    ip=$(dig +short @1.1.1.1 "$host" | head -1)
    c=$(curl -s -m 8 -o /dev/null -w '%{http_code}' --resolve "$host:443:$ip" "$url/health"); [ "$c" = 200 ] && break; sleep 3
  done
  log "tunnel $url health=$c"
  [ "$c" = 200 ] || return
  mkdir -p "$RUN/web-deploy/.vercel"; cp "$ROOT/web/.vercel/project.json" "$RUN/web-deploy/.vercel/" 2>/dev/null
  rsync -a --delete --exclude node_modules --exclude .next --exclude .env.local --exclude .vercel "$ROOT/web/" "$RUN/web-deploy/"
  ( cd "$RUN/web-deploy" \
    && npx --yes vercel@latest env rm API_URL production --yes < /dev/null 2>&1 | /usr/bin/grep -iE "removed|error" >> "$LOG"
    printf %s "$url" | ( cd "$RUN/web-deploy" && npx --yes vercel@latest env add API_URL production 2>&1 | /usr/bin/grep -iE "added|error" >> "$LOG" )
    cd "$RUN/web-deploy" && npx --yes vercel@latest deploy --prod --yes < /dev/null 2>&1 | /usr/bin/grep -E "Aliased|readyState|rror" >> "$LOG" )
  log "repair finished; site check: $(code "$SITE/api/backend/auth/me" 25)"
}

pass() {
  backend_up || { sleep 3; backend_up || start_backend; }
  start_models
  if site_ok; then rm -f "$RUN/bad"; return; fi
  local n=$(( $(cat "$RUN/bad" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$RUN/bad"
  log "site check failed ($n in a row)"
  [ "$n" -ge 2 ] && backend_up && repoint
}

if [ "${1:-}" = "--once" ]; then pass; else while true; do pass; sleep "$INTERVAL"; done; fi
