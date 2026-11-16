#!/usr/bin/env bash
set -euo pipefail

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.stack-test.yml)

cleanup() {
    echo "Tearing down..."
    "${COMPOSE[@]}" down -v --remove-orphans 2>/dev/null || true
}
trap cleanup EXIT

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
"$(command -v python3 || command -v python)" scripts/stack_stream_check.py

echo "All smoke tests passed."
