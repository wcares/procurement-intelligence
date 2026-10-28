#!/bin/bash
# Restart the public tunnel, point the Vercel site at the new address, redeploy, and check it. Takes about two minutes.
#   scripts/restart-tunnel.sh
# Use it when the site shows 502 or 530 (the tunnel dropped). The backend must be running on :8000.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="${PROCINTEL_RUN_DIR:-$HOME/.procintel-demo}"; mkdir -p "$RUN"
SITE="${PROCINTEL_SITE:-https://procintel-demo.vercel.app}"

if [ "$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)" != 200 ]; then
  echo "The backend is not answering on 127.0.0.1:8000. Start it first (README, section 4), then run this again."; exit 1
fi

echo "1/4 restarting the tunnel"
URL=""
for attempt in 1 2 3; do   # Cloudflare sometimes hands out an address and never connects: start again
  pkill -f "cloudflared tunnel"; sleep 1
  nohup cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8000 > "$RUN/tunnel.log" 2>&1 &
  for i in $(seq 1 25); do /usr/bin/grep -q "Registered tunnel connection" "$RUN/tunnel.log" && break; sleep 2; done
  /usr/bin/grep -q "Registered tunnel connection" "$RUN/tunnel.log" && { URL=$(/usr/bin/grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$RUN/tunnel.log" | head -1); break; }
  echo "    attempt $attempt did not connect to Cloudflare; trying again"
done
[ -n "$URL" ] || { echo "The tunnel would not connect after 3 tries; see $RUN/tunnel.log. Try again in a few minutes."; exit 1; }
echo "    new address: $URL"

echo "2/4 waiting for the address to answer"   # this Mac's resolver can lag behind a new name; try Cloudflare's and Google's too
HOST="${URL#https://}"; C=""
for i in $(seq 1 30); do
  C=$(curl -s -m 6 -o /dev/null -w '%{http_code}' "$URL/health"); [ "$C" = 200 ] && break
  for DNS in 1.1.1.1 8.8.8.8; do
    IP=$(dig +short @"$DNS" "$HOST" | head -1); [ -n "$IP" ] || continue
    C=$(curl -s -m 6 -o /dev/null -w '%{http_code}' --resolve "$HOST:443:$IP" "$URL/health"); [ "$C" = 200 ] && break 2
  done
  sleep 3
done
# Not fatal: the tunnel is registered, and Vercel's own resolvers may know the name before this Mac's do. Step 4 is the real test.
[ "$C" = 200 ] || echo "    this Mac cannot reach the new address yet (status ${C:-none}); continuing, step 4 will tell"

echo "3/4 pointing the site at it and redeploying"
mkdir -p "$RUN/web-deploy/.vercel"; cp "$ROOT/web/.vercel/project.json" "$RUN/web-deploy/.vercel/" 2>/dev/null
rsync -a --delete --exclude node_modules --exclude .next --exclude .env.local --exclude .vercel "$ROOT/web/" "$RUN/web-deploy/"
cd "$RUN/web-deploy" || exit 1
npx --yes vercel@latest env rm API_URL production --yes < /dev/null 2>&1 | /usr/bin/grep -iE "removed|error"
printf %s "$URL" | npx --yes vercel@latest env add API_URL production 2>&1 | /usr/bin/grep -iE "added|error"
npx --yes vercel@latest deploy --prod --yes < /dev/null 2>&1 | /usr/bin/grep -E "Aliased|readyState|rror"

echo "4/4 checking the site (401 = reachable; a fresh deploy can take a minute to warm up)"
for i in $(seq 1 12); do
  C=$(curl -s -m 25 -o /dev/null -w '%{http_code}' "$SITE/api/backend/auth/me"); echo "    $C"
  if [ "$C" = 401 ] || [ "$C" = 200 ]; then echo "Done: $SITE is up."; exit 0; fi; sleep 5
done
echo "The site still does not reach the backend. Run this script once more."; exit 1
