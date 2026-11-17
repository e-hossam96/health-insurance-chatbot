#!/usr/bin/env bash
set -euo pipefail

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.stack-test.yml)
PYTHON="$(command -v python3 || command -v python)"
export GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-smoke-$(date +%s)}"

echo "Validating the Prometheus config with promtool..."
MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W 2>/dev/null || pwd)/observability:/config:ro" --entrypoint promtool prom/prometheus:v3.16.0 check config /config/prometheus.yml

CADDY_IMAGE=caddy:2.11.9-alpine
CADDY_SMOKE=health-chatbot-caddy-smoke
CADDYFILE_MOUNT="$(pwd -W 2>/dev/null || pwd)/Caddyfile:/etc/caddy/Caddyfile:ro"
SCRATCH="$(mktemp -d)"

cleanup() {
    echo "Tearing down..."
    docker rm -f "$CADDY_SMOKE" >/dev/null 2>&1 || true
    "${COMPOSE[@]}" down -v --remove-orphans 2>/dev/null || true
    rm -rf "$SCRATCH"
}
trap cleanup EXIT

echo "Validating the production Caddyfile..."
MSYS_NO_PATHCONV=1 docker run --rm -e DOMAIN=example.test -e LETSENCRYPT_EMAIL=ops@example.test -v "$CADDYFILE_MOUNT" "$CADDY_IMAGE" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

echo "Building and starting the stack (fake model server instead of real models)..."
"${COMPOSE[@]}" up -d --build --wait --wait-timeout 300

echo "Testing /health through frontend proxy..."
status=$(curl -sf -o /dev/null -w '%{http_code}' http://localhost/api/health)
if [ "$status" != "200" ]; then
    echo "FAIL: /api/health returned $status, expected 200"
    exit 1
fi
echo "OK: /api/health returned 200"

echo "Testing index page loads..."
body=$(curl -sf http://localhost/)
if ! echo "$body" | grep -q '<div id="root"'; then
    echo "FAIL: index page does not contain root div"
    exit 1
fi
echo "OK: index page loads"

echo "Testing /metrics is not public (H6)..."
status=$(curl -s -o /dev/null -w '%{http_code}' http://localhost/api/metrics)
if [ "$status" != "404" ]; then
    echo "FAIL: /api/metrics returned $status through nginx, expected 404"
    exit 1
fi
for variant in "/api/metrics/" "/api/metrics?format=text"; do
    status=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost${variant}")
    if [ "$status" != "404" ]; then
        echo "FAIL: ${variant} returned $status through nginx, expected 404"
        exit 1
    fi
done
echo "OK: /api/metrics is blocked through nginx"

for path in /api/docs /api/redoc /api/openapi.json; do
    status=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost${path}")
    if [ "$status" != "404" ]; then
        echo "FAIL: ${path} returned $status through nginx, expected 404"
        exit 1
    fi
done
echo "OK: the API docs and schema are not served"

# capture first: grep -q closes the pipe early and curl's SIGPIPE fails the check under pipefail
index_headers=$(curl -s -D - -o /dev/null http://localhost/ || true)
if ! grep -qi "^content-security-policy: default-src 'self'" <<<"$index_headers"; then
    echo "FAIL: the index page has no Content-Security-Policy header"
    exit 1
fi
echo "OK: nginx sends the Content-Security-Policy"

if [ "$("${COMPOSE[@]}" exec -T backend id -u | tr -d '\r')" = "0" ]; then
    echo "FAIL: the backend container runs as root"
    exit 1
fi
echo "OK: the backend runs as a non-root user"

if [ "$("${COMPOSE[@]}" exec -T frontend id -u | tr -d '\r')" = "0" ]; then
    echo "FAIL: the frontend container runs as root"
    exit 1
fi
echo "OK: the frontend nginx runs as a non-root user"

echo "Testing the internal scrape of /metrics..."
scraped_metrics=$("${COMPOSE[@]}" exec -T prometheus wget -qO- http://backend:8000/metrics || true)
if ! grep -q '^http_requests_total' <<<"$scraped_metrics"; then
    echo "FAIL: /metrics is not reachable from Prometheus"
    exit 1
fi
echo "OK: Prometheus reaches /metrics on the metrics network"

echo "Testing network isolation..."
for target in postgres:5432 qdrant:6333 prometheus:9090 grafana:3000; do
    if "${COMPOSE[@]}" exec -T frontend wget -q -T 3 -O /dev/null "http://${target}/" 2>/dev/null; then
        echo "FAIL: the frontend reaches ${target}"
        exit 1
    fi
    if "${COMPOSE[@]}" exec -T frontend nslookup "${target%%:*}" >/dev/null 2>&1; then
        echo "FAIL: the frontend can resolve ${target%%:*}"
        exit 1
    fi
done
echo "OK: the frontend cannot see the databases or the dashboards"

echo "Starting Caddy in front of nginx, as in production..."
MSYS_NO_PATHCONV=1 docker run -d --name "$CADDY_SMOKE" --network health-chatbot-edge --ip 172.31.250.250 \
    -e DOMAIN=localhost -e LETSENCRYPT_EMAIL=ops@example.test -v "$CADDYFILE_MOUNT" \
    -p 127.0.0.1:8443:443 -p 127.0.0.1:8880:80 "$CADDY_IMAGE" >/dev/null
for _ in $(seq 1 30); do
    if MSYS_NO_PATHCONV=1 docker exec "$CADDY_SMOKE" cat /data/caddy/pki/authorities/local/root.crt > "$SCRATCH/caddy-root.crt" 2>/dev/null \
        && curl -sf --ssl-no-revoke --cacert "$SCRATCH/caddy-root.crt" -o /dev/null https://localhost:8443/api/health; then
        break
    fi
    sleep 1
done
headers=$(curl -sf --ssl-no-revoke --cacert "$SCRATCH/caddy-root.crt" -D - -o /dev/null https://localhost:8443/api/health) || {
    echo "FAIL: /api/health is not served over HTTPS by Caddy"
    docker logs "$CADDY_SMOKE" 2>&1 | tail -20
    exit 1
}
echo "$headers" | grep -qi '^strict-transport-security: max-age=31536000' || { echo "FAIL: Caddy sends no HSTS header"; exit 1; }
if echo "$headers" | grep -qi '^server:'; then
    echo "FAIL: Caddy names itself in the Server header"
    exit 1
fi
caddy_index_headers=$(curl -sf --ssl-no-revoke --cacert "$SCRATCH/caddy-root.crt" -D - -o /dev/null https://localhost:8443/ || true)
grep -qi "^content-security-policy: default-src 'self'" <<<"$caddy_index_headers" \
    || { echo "FAIL: the CSP from nginx does not pass through Caddy"; exit 1; }
status=$(curl -s --ssl-no-revoke --cacert "$SCRATCH/caddy-root.crt" -o /dev/null -w '%{http_code}' https://localhost:8443/api/metrics)
[ "$status" = "404" ] || { echo "FAIL: /api/metrics returned $status through Caddy, expected 404"; exit 1; }
location=$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' http://localhost:8880/)
case "$location" in
    30[178]\ https://*) ;;
    *) echo "FAIL: plain HTTP is not redirected to HTTPS ($location)"; exit 1 ;;
esac
echo "OK: Caddy serves HTTPS with HSTS, keeps the nginx headers and redirects HTTP"

echo "Testing which client address nginx records (F15)..."
via_caddy="realip-caddy-$RANDOM$RANDOM"
direct="realip-direct-$RANDOM$RANDOM"
curl -s --ssl-no-revoke --cacert "$SCRATCH/caddy-root.crt" -o /dev/null -H 'X-Forwarded-For: 198.51.100.7' "https://localhost:8443/?${via_caddy}"
curl -s -o /dev/null -H 'X-Forwarded-For: 198.51.100.7' "http://localhost/?${direct}"
caddy_client=$(docker logs health-chatbot-frontend 2>/dev/null | grep "$via_caddy" | awk '{print $1}' | tail -1)
direct_client=$(docker logs health-chatbot-frontend 2>/dev/null | grep "$direct" | awk '{print $1}' | tail -1)
if [ -z "$caddy_client" ] || [ -z "$direct_client" ]; then
    echo "FAIL: the marker requests are missing from the nginx log"
    exit 1
fi
if [ "$caddy_client" = "198.51.100.7" ] || [ "$direct_client" = "198.51.100.7" ]; then
    echo "FAIL: a client chose its own address (via Caddy: $caddy_client, direct: $direct_client)"
    exit 1
fi
if [ "$caddy_client" = "172.31.250.250" ]; then
    echo "FAIL: nginx records Caddy's address, so every visitor shares one rate-limit bucket"
    exit 1
fi
echo "OK: nginx takes the client address from Caddy only (via Caddy: $caddy_client, direct: $direct_client)"

echo "Seeding a location and an admin..."
SMOKE_ADMIN="smoke-admin-$(date +%s)"
"${COMPOSE[@]}" exec -T -e SMOKE_ADMIN="$SMOKE_ADMIN" backend sh -c 'python scripts/create_admin.py --username "$SMOKE_ADMIN" --password adminpass1 --name "Admin One" --location Cairo'

echo "Testing a KB upload and ingestion as the non-root backend user..."
SMOKE_ADMIN="$SMOKE_ADMIN" "$PYTHON" scripts/stack_kb_check.py

echo "Testing a streamed chat turn through Caddy and nginx..."
STACK_URL=https://localhost:8443 STACK_CA_PEM="$(cat "$SCRATCH/caddy-root.crt")" "$PYTHON" scripts/stack_stream_check.py

echo "Testing Prometheus targets and Grafana dashboards..."
"$PYTHON" scripts/stack_observability_check.py

if [ "${STACK_E2E:-0}" = "1" ]; then
    echo "Seeding demo data and admin1 for the stack e2e tests..."
    "${COMPOSE[@]}" exec -T backend python scripts/seed.py
    "${COMPOSE[@]}" exec -T backend python scripts/create_admin.py --username admin1 --password adminpass1 --name "Admin One" --location Cairo         || echo "admin1 already exists"
    echo "Running the Playwright stack e2e suite..."
    (cd frontend && npx playwright test -c playwright.stack.config.ts)
fi

echo "All smoke tests passed."
