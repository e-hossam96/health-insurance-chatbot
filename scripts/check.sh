#!/usr/bin/env bash
set -euo pipefail

cmd="${1:-check}"

case "$cmd" in
  lint)
    echo "=== ruff ==="
    uv run ruff check
    echo "=== oxlint ==="
    cd frontend && npx oxlint
    ;;
  typecheck)
    echo "=== mypy ==="
    uv run mypy
    echo "=== tsc ==="
    cd frontend && npx tsc --noEmit -p tsconfig.app.json
    ;;
  test-backend)
    uv run pytest
    ;;
  test-frontend)
    cd frontend && npx vitest run
    ;;
  test)
    bash "$0" test-backend
    bash "$0" test-frontend
    ;;
  check)
    bash "$0" lint
    bash "$0" typecheck
    bash "$0" test
    ;;
  e2e)
    cd frontend && npx playwright test
    ;;
  evals)
    echo "Not available before phase 6"
    ;;
  smoke)
    bash scripts/smoke_compose.sh
    ;;
  *)
    echo "Usage: $0 {check|lint|typecheck|test|test-backend|test-frontend|e2e|evals|smoke}"
    exit 1
    ;;
esac
