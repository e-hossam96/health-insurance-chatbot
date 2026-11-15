#!/usr/bin/env bash
set -euo pipefail

cleanup() {
    echo "Tearing down..."
    docker compose down -v --remove-orphans 2>/dev/null || true
}
trap cleanup EXIT

echo "Building and starting the stack..."
docker compose up -d --build --wait --wait-timeout 120

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

echo "All smoke tests passed."
