#!/bin/bash
# Manual control of the demo services, from a menu: see which are up, read or follow a service's log, and start, stop
# or restart one service at a time.
#   scripts/control.sh
# scripts/fix-demo.sh is the automatic repair; this script changes only what you pick. It starts the backend with the
# same command as the watchdog (.env.example, then .env), so sign-in stays on.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
cd "$(dirname "$0")/.." || exit 1
. scripts/demo-watchdog.sh      # RUN, SITE, MODELS, LAYA, code, backend_up, model_up, start_backend, start_model

if [ -t 1 ]; then G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; D=$'\033[2m'; B=$'\033[1m'; N=$'\033[0m'; else G=; R=; Y=; D=; B=; N=; fi
DEFAULT_LINES=50
SERVICES="backend web m8080 m8081 m8082 m8083 tunnel db watchdog"

name() {
  case "$1" in
    backend) echo "Backend API :8000";;            web)    echo "Web app, local copy :3100";;
    m8080)   echo "Saluki 27B, answers :8080";;     m8081)  echo "EmbeddingGemma, search :8081";;
    m8082)   echo "Laya, checks and tags :8082";;   m8083)  echo "Qwen3-VL, figures :8083";;
    tunnel)  echo "Cloudflare tunnel";;             db)     echo "Postgres + pgAdmin containers";;
    watchdog) echo "Watchdog (automatic repair loop)";;
  esac
}
port() { case "$1" in backend) echo 8000;; web) echo 3100;; m80*) echo "${1#m}";; esac; }
pid_on() { lsof -t -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | head -1; }
svc_at() { local i=0 s; for s in $SERVICES; do i=$((i + 1)); [ "$i" = "$1" ] && { echo "$s"; return; }; done; }

is_up() {
  case "$1" in
    backend)  backend_up;;
    web)      [ "$(code http://127.0.0.1:3100/ 5)" = 200 ];;
    m80*)     model_up "$(port "$1")";;
    tunnel)   pgrep -f "cloudflared tunnel" > /dev/null;;
    db)       docker ps --format '{{.Names}}' 2>/dev/null | /usr/bin/grep -q procintel-db;;
    watchdog) pgrep -f "demo-watchdog.sh" > /dev/null;;
  esac
}
state() { if is_up "$1"; then echo "${G}UP  ${N}"; else echo "${R}DOWN${N}"; fi; }

# The file the running process writes to (its standard output), else where this script and the watchdog start it.
log_file() {
  local p pid f
  case "$1" in tunnel) echo "$RUN/tunnel.log"; return;; watchdog) echo "$RUN/watchdog.log"; return;; db) return;; esac
  p=$(port "$1"); pid=$(pid_on "$p")
  if [ -n "$pid" ]; then
    f=$(lsof -a -p "$pid" -d 1 -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)
    [ -f "$f" ] && { echo "$f"; return; }
  fi
  case "$1" in backend) echo "$RUN/api.log";; web) echo "$RUN/web.log";; *) echo "$RUN/model-$p.log";; esac
}

show_log() {   # service, lines, follow (1 or empty)
  local f
  if [ "$1" = db ]; then
    if [ -n "$3" ]; then trap ':' INT; docker compose -f compose.db.yaml logs -f --tail "$2"; trap - INT
    else docker compose -f compose.db.yaml logs --tail "$2"; fi
    return
  fi
  f=$(log_file "$1")
  [ -f "$f" ] || { echo "   no log file yet ($f)"; return; }
  echo "${D}   $f${N}"
  if [ -n "$3" ]; then echo "${D}   following; press Ctrl-C to come back to the menu${N}"; trap ':' INT; tail -n "$2" -f "$f"; trap - INT
  else tail -n "$2" "$f"; fi
}

wait_state() {   # service, up|down, seconds
  local i
  for i in $(seq 1 "$3"); do
    if [ "$2" = up ]; then is_up "$1" && { echo "   ${G}up${N}"; return 0; }
    else is_up "$1" || { echo "   ${G}stopped${N}"; return 0; }; fi
    sleep 1
  done
  echo "   ${R}still not $2 after $3 s${N}; check its log"; return 1
}
confirm() { local a; read -r -p "   $1 [y/N] " a; [ "$a" = y ] || [ "$a" = Y ]; }
watchdog_note() { pgrep -f "demo-watchdog.sh" > /dev/null && echo "   ${Y}note:${N} the watchdog is running and will start the backend and models 8080-8082 again within a minute"; }

start_svc() {
  case "$1" in
    backend) start_backend; wait_state backend up 120;;
    web)
      [ -d web/.next ] || { echo "   no build yet: run (cd web && npm run build) first"; return; }
      # only the server goes to the background (with "cd web && ... &" a copy of this script would, holding the terminal)
      ( cd web || exit 1; API_URL=http://127.0.0.1:8000 nohup npx next start -p 3100 >> "$RUN/web.log" 2>&1 < /dev/null & )
      wait_state web up 40;;
    m8080) start_model 8080 -m "$MODELS/underdog-saluki-27b-1.0-iq2.gguf" --alias saluki-27b -c 8192 -np 1; wait_state m8080 up 180;;
    m8081) start_model 8081 -m "$MODELS/embeddinggemma-2-q8_0.gguf" --embedding --alias embeddinggemma-2 -c 8192 -b 2048 -ub 2048 -np 4; wait_state m8081 up 180;;
    m8082) start_model 8082 -m "$LAYA" --alias laya -c 8192 -b 2048 -ub 2048 -np 1; wait_state m8082 up 180;;
    m8083) start_model 8083 -m "$MODELS/qwen3-vl-8b.gguf" --mmproj "$MODELS/qwen3-vl-8b-mmproj.gguf" --alias qwen3-vl-8b -c 8192 -np 1; wait_state m8083 up 180;;
    tunnel)
      echo "   a new tunnel has a new address: the site is pointed at it and redeployed (about 2 minutes)"
      confirm "Start a new tunnel?" && scripts/restart-tunnel.sh;;
    db)
      docker ps > /dev/null 2>&1 || { echo "   starting Colima"; colima start --cpu 2 --memory 3 2>&1 | tail -2; }
      docker compose -f compose.db.yaml up -d 2>&1 | tail -3;;
    watchdog) nohup scripts/demo-watchdog.sh >> "$RUN/watchdog.out" 2>&1 & sleep 1; wait_state watchdog up 5;;
  esac
}

stop_svc() {
  local pid
  case "$1" in
    backend|web|m80*)
      pid=$(pid_on "$(port "$1")")
      [ -n "$pid" ] || { echo "   not running"; return; }
      kill "$pid"; wait_state "$1" down 20; [ "$1" = web ] || watchdog_note;;
    tunnel)
      echo "   the public site stops working until a new tunnel is started (start = new address + redeploy)"
      confirm "Stop the tunnel?" && { pkill -f "cloudflared tunnel"; wait_state tunnel down 10; };;
    db) docker compose -f compose.db.yaml stop 2>&1 | tail -3;;
    watchdog) pkill -f "demo-watchdog.sh"; wait_state watchdog down 10;;
  esac
}

restart_svc() {
  case "$1" in
    tunnel) start_svc tunnel;;   # restart-tunnel.sh replaces the running tunnel itself
    backend)
      echo "   the public site shows errors for the 20-60 s the backend takes to start"
      confirm "Restart the backend?" || return
      stop_svc backend && start_svc backend;;
    *) is_up "$1" && stop_svc "$1"; start_svc "$1";;
  esac
}

ask_lines() {
  local n; read -r -p "   How many lines? [$DEFAULT_LINES] " n; n=${n:-$DEFAULT_LINES}
  case "$n" in ''|*[!0-9]*) echo "$DEFAULT_LINES";; *) echo "$n";; esac
}

service_menu() {
  local c n
  while true; do
    echo; echo "${B}$(name "$1")${N}  $(state "$1")"
    [ "$1" = db ] && echo "${D}   logs: docker compose -f compose.db.yaml logs${N}" || echo "${D}   log: $(log_file "$1")${N}"
    echo "  1) Show the last lines of the log     2) Follow the log live (Ctrl-C to come back)"
    echo "  3) Restart     4) Stop     5) Start     b) Back"
    read -r -p "> " c || exit 0
    case "$c" in
      1) n=$(ask_lines); echo; show_log "$1" "$n";;
      2) n=$(ask_lines); echo; show_log "$1" "$n" 1;;
      3) restart_svc "$1";;
      4) if [ "$1" = backend ] || [ "$1" = watchdog ]; then confirm "Stop $(name "$1")?" && stop_svc "$1"; else stop_svc "$1"; fi;;
      5) if is_up "$1"; then echo "   already up"; else start_svc "$1"; fi;;
      b|B|"") return;;
      *) echo "   pick 1-5 or b";;
    esac
  done
}

main_menu() {
  local c i s svc site
  while true; do
    echo; echo "${B}Demo services${N}, $(date '+%a %H:%M:%S')"
    i=0; for s in $SERVICES; do i=$((i + 1)); printf '  %s) %s %s\n' "$i" "$(state "$s")" "$(name "$s")"; done
    site=$(code "$SITE/api/backend/auth/me" 10)
    case "$site" in 200|401) echo "     ${G}OK  ${N} public site reaches the backend ($site)";; *) echo "     ${R}FAIL${N} public site does not reach the backend (${site:-none}): try scripts/fix-demo.sh";; esac
    echo; read -r -p "Pick a service (1-9), r to refresh, q to quit: " c || exit 0
    case "$c" in
      [1-9]) svc=$(svc_at "$c"); service_menu "$svc";;
      r|R|"") ;;
      q|Q) exit 0;;
      *) echo "   pick 1-9, r or q";;
    esac
  done
}

main_menu
