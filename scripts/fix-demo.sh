#!/bin/bash
# Demo helper. Run it from a terminal in the project folder, e.g. after the lid was closed.
#   scripts/fix-demo.sh            health check, then fixes whatever is broken, then checks again (the default)
#   scripts/fix-demo.sh --check    health check only, changes nothing
#   scripts/fix-demo.sh --menu     a menu: restart one part, replace the tunnel, restart containers, check the network
#   scripts/fix-demo.sh --force    as the default, but replace the tunnel and redeploy even if the site looks fine
# It never starts anything with sign-in off. Nothing is installed; what it starts is what the demo needs.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
cd "$(dirname "$0")/.." || exit 1
. scripts/demo-watchdog.sh      # the same checks and start commands the watchdog uses

if [ -t 1 ]; then G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; D=$'\033[2m'; N=$'\033[0m'; else G=; R=; Y=; D=; N=; fi
row() { printf '  %s %-34s %s\n' "$1" "$2" "$3"; }
ok()  { row "${G}OK  ${N}" "$1" "$2"; }
bad() { row "${R}FAIL${N}" "$1" "$2"; FAILS=$((FAILS + 1)); }
note(){ row "${Y}note${N}" "$1" "$2"; }
step(){ echo; echo "${D}== $*${N}"; }

health() {   # prints the table; FAILS = how many checks failed
  FAILS=0
  echo; echo "Health, $(date '+%a %H:%M:%S')"
  [ "$(code https://www.cloudflare.com 6)" != 000 ] && ok "Internet" "reachable" || bad "Internet" "no connection: check wifi"
  for p in 8080 8081 8082; do
    n=$([ "$p" = 8080 ] && echo "answers (Saluki 27B)" || { [ "$p" = 8081 ] && echo "embeddings (EmbeddingGemma)" || echo "decisions (Laya)"; })
    [ "$(code http://127.0.0.1:$p/health)" = 200 ] && ok "Model :$p" "$n" || bad "Model :$p" "$n is not answering"
  done
  [ "$(code http://127.0.0.1:8000/health)" = 200 ] && ok "Backend :8000" "answering" || bad "Backend :8000" "not answering"
  a=$(code http://127.0.0.1:8000/auth/me)
  if [ "$a" = 401 ]; then ok "Sign-in" "required (as it should be)"; elif [ "$a" = 200 ]; then bad "Sign-in" "IS OFF: anyone can use it. Restart the backend with sign-in on"; else note "Sign-in" "backend down, cannot tell"; fi
  if pgrep -f "cloudflared tunnel" > /dev/null; then ok "Tunnel process" "running"; else bad "Tunnel process" "not running"; fi
  s=$(code "$SITE/api/backend/auth/me" 25)
  case "$s" in 401|200) ok "Site -> backend" "reachable ($s)";; 530|502) bad "Site -> backend" "$s: the tunnel is down or points elsewhere";; *) bad "Site -> backend" "status ${s:-none}";; esac
  [ "$(code "$SITE/login" 20)" = 200 ] && ok "Site login page" "loads" || bad "Site login page" "does not load"
  if command -v docker > /dev/null && docker ps > /dev/null 2>&1; then
    c=$(docker ps --format '{{.Names}}' | /usr/bin/grep -c procintel); note "Containers (optional)" "$c procintel container(s) running; the demo does not need them"
  fi
  echo; [ "$FAILS" = 0 ] && echo "${G}All checks pass.${N}" || echo "${R}$FAILS check(s) failed.${N}"
}

wait_for() { local what="$1" secs="$2"; shift 2; for i in $(seq 1 "$secs"); do "$@" && { echo "   $what: up"; return 0; }; sleep 1; done; echo "   $what: NOT up after ${secs}s"; return 1; }
stay_awake() { pkill -f "caffeinate -i -s -t 28800" 2>/dev/null; nohup caffeinate -i -s -t 28800 > /dev/null 2>&1 & echo "   keeping the Mac awake for 8 hours (a closed lid still sleeps it)"; }
fix_models()  { start_models; for p in 8080 8081 8082; do wait_for "model :$p" 180 model_up "$p"; done; }
fix_backend() { backend_up || start_backend; wait_for "backend" 120 backend_up; }
fix_tunnel()  { backend_up && scripts/restart-tunnel.sh || echo "   the backend is not up, so a new tunnel would not help"; }
restart_backend() { pkill -f "uvicorn procintel.api.app"; sleep 2; start_backend; wait_for "backend" 120 backend_up; }
restart_models()  { pkill -f "llama-server"; sleep 2; fix_models; }
containers() {
  command -v docker > /dev/null || { echo "   docker is not installed"; return; }
  docker ps > /dev/null 2>&1 || { echo "   starting Colima"; colima start --cpu 2 --memory 3 2>&1 | tail -2; }
  docker compose -f compose.db.yaml up -d 2>&1 | tail -3; docker ps --format '   {{.Names}}  {{.Status}}'
}
network() {
  step "network"
  for h in www.cloudflare.com api.cloudflare.com vercel.com "$(echo "${SITE#https://}")"; do
    printf '   %-30s system DNS: %-3s  Cloudflare DNS: %s\n' "$h" "$([ -n "$(dig +short "$h" | head -1)" ] && echo ok || echo NO)" "$([ -n "$(dig +short @1.1.1.1 "$h" | head -1)" ] && echo ok || echo NO)"
  done
  echo "   if system DNS says NO while Cloudflare DNS says ok, flush this Mac's DNS cache: sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder"
  echo "   tunnel log, last lines:"; tail -3 "$RUN/tunnel.log" 2>/dev/null | cut -c1-140 | sed 's/^/     /'
}

fix_all() {
  step "keeping the Mac awake"; stay_awake
  step "model servers";  fix_models
  step "backend";        fix_backend
  step "public site"
  if [ "$FORCE" = 1 ] || ! site_ok; then fix_tunnel; else echo "   the site reaches the backend already"; fi
}

menu() {
  while true; do
    echo; echo "What do you want to do?"
    echo "  1) Health check                      5) Replace the tunnel and redeploy the site"
    echo "  2) Fix everything that is broken     6) Start or restart the database containers (Colima/Docker)"
    echo "  3) Restart the backend               7) Check the network (DNS, Cloudflare, Vercel)"
    echo "  4) Restart the model servers         q) Quit"
    read -r -p "> " c
    case "$c" in
      1) health;; 2) health; [ "$FAILS" = 0 ] || { fix_all; health; };; 3) step "backend"; restart_backend;; 4) step "models"; restart_models;;
      5) step "tunnel"; fix_tunnel;; 6) step "containers"; containers;; 7) network;; q|Q) return;; *) echo "pick 1-7 or q";;
    esac
  done
}

FORCE=0
case "${1:-}" in
  --check) health; [ "$FAILS" = 0 ]; exit $?;;
  --menu)  menu; exit 0;;
  --force) FORCE=1;;
  "")      ;;
  *)       echo "usage: scripts/fix-demo.sh [--check | --menu | --force]"; exit 2;;
esac
health
if [ "$FAILS" = 0 ] && [ "$FORCE" = 0 ]; then exit 0; fi
echo; echo "Fixing what is broken..."
fix_all
health
[ "$FAILS" = 0 ] && { echo; echo "${G}Ready: $SITE${N}"; exit 0; }
echo; echo "${R}Still not all good.${N} Run it again; if it fails the same way, send Claude the table above."; exit 1
