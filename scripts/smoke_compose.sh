#!/usr/bin/env bash
set -euo pipefail

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.stack-test.yml)
PYTHON="$(command -v python3 || command -v python)"
export GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-smoke-$(date +%s)}"

echo "Validating the Prometheus config with promtool..."
MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W 2>/dev/null || pwd)/observability:/config:ro" --entrypoint promtool prom/prometheus:v3.0.1 check config /config/prometheus.yml

cleanup() {
    echo "Tearing down..."
    "${COMPOSE[@]}" down -v --remove-orphans 2>/dev/null || true
}
trap cleanup EXIT

echo "Validating the production nginx template with a throwaway certificate..."
MSYS_NO_PATHCONV=1 docker run --rm --add-host backend:127.0.0.1 -e DOMAIN=example.test     -v "$(pwd -W 2>/dev/null || pwd)/frontend/nginx.prod.conf.template:/etc/nginx/templates/default.conf.template:ro"     nginx:1.27-alpine sh -c 'apk add --no-cache openssl >/dev/null && mkdir -p /etc/letsencrypt/live/example.test         && openssl req -x509 -nodes -newkey rsa:2048 -days 1 -subj /CN=example.test -keyout /etc/letsencrypt/live/example.test/privkey.pem -out /etc/letsencrypt/live/example.test/fullchain.pem 2>/dev/null         && /docker-entrypoint.sh nginx -t'

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

echo "Testing the internal scrape of /metrics..."
if ! "${COMPOSE[@]}" exec -T frontend wget -qO- http://backend:8000/metrics | grep -q '^http_requests_total'; then
    echo "FAIL: /metrics is not reachable on the internal network"
    exit 1
fi
echo "OK: /metrics is reachable inside the Docker network"

echo "Seeding a location and an admin..."
"${COMPOSE[@]}" exec -T backend sh -c 'python scripts/create_admin.py --database-url "$DATABASE_URL" --username "smoke-admin-$(date +%s)" --password adminpass1 --name "Admin One" --location Cairo'

echo "Testing a streamed chat turn through nginx..."
"$PYTHON" scripts/stack_stream_check.py

echo "Testing Prometheus targets and Grafana dashboards..."
"$PYTHON" scripts/stack_observability_check.py

if [ "${STACK_E2E:-0}" = "1" ]; then
    echo "Seeding demo data and admin1 for the stack e2e tests..."
    "${COMPOSE[@]}" exec -T backend sh -c 'python scripts/seed.py --database-url "$DATABASE_URL"'
    "${COMPOSE[@]}" exec -T backend sh -c 'python scripts/create_admin.py --database-url "$DATABASE_URL" --username admin1 --password adminpass1 --name "Admin One" --location Cairo'         || echo "admin1 already exists"
    echo "Running the Playwright stack e2e suite..."
    (cd frontend && npx playwright test -c playwright.stack.config.ts)
fi

echo "All smoke tests passed."
