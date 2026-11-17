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
  test-e2e-mocked)
    cd frontend && npx playwright test e2e/chat.spec.ts e2e/kb.spec.ts e2e/admin.spec.ts
    ;;
  test)
    bash "$0" test-backend
    bash "$0" test-frontend
    bash "$0" test-e2e-mocked
    ;;
  check)
    bash "$0" lint
    bash "$0" typecheck
    bash "$0" test
    ;;
  e2e)
    STACK_E2E=1 bash scripts/smoke_compose.sh
    ;;
  evals)
    echo "The evals call real models and cost money. Run a suite explicitly:"
    echo "  uv run python -m chatbot_ai.evals <ingest|routing|retrieval|answers|tools|all> [--smoke] [--set KEY=VALUE]"
    ;;
  smoke-models)
    PYTHONPATH=. uv run python scripts/smoke_real_models.py
    ;;
  smoke)
    bash scripts/smoke_compose.sh
    ;;
  *)
    echo "Usage: $0 {check|lint|typecheck|test|test-backend|test-frontend|test-e2e-mocked|e2e|evals|smoke|smoke-models}"
    exit 1
    ;;
esac
