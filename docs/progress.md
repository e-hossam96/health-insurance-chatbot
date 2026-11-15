# Progress

State file for Claude Code. Read it at the start of every session and update it after every step. The rules for using it are in `CLAUDE.md` (Working agreement).

## Status

| Phase | Name | Status | Last step done |
|---|---|---|---|
| 0 | Skeleton and test harness | done | 0.7 |
| 1 | Data model | done | 1.3 |
| 2 | Accounts and access | done | 2.6 |
| 3 | Admin catalog and slots | done | 3.5 |
| 4 | Visits and complaints | done | 4.6 |
| 5 | Chat shell with a stub | not started | - |
| 6 | AI package | not started | - |
| 7 | Observability | not started | - |
| 8 | Hardening and demo | not started | - |

Status values: not started, in progress, done, blocked (say why below).

## Next step

Phase 5, step 5.1.

## Needs confirmation

Questions for the user that do not block the current step. Format: `- [phase.step] question (options, your recommendation)`.

- none

## Gates

- [ ] Gate 1 real model calls: API key, model names per role, embedding dimensions
- [ ] Gate 2 eval datasets and fixtures approved
- [ ] Gate 3 branding, instance size, domain, SSL
- [ ] Gate 4 paid eval run approved

## Decisions log

Choices made without asking. Format: `- [phase.step] decision - why`.

- [0.1] Renamed `docs/specs/` to `docs/spec/` - the CLAUDE.md references `docs/spec/`; the files were created as `docs/specs/`.
- [0.1] Removed `[build-system]` from root `pyproject.toml` - it's a workspace root, not a package; avoids the "Expected a Python module" error.
- [0.3] Using `scripts/check.sh` as the task runner instead of a Makefile - Windows has no `make`; the Makefile delegates to the script so CI (Linux) still works.
- [0.4] Added `pyyaml` as a dev dependency for the rule coverage tool.
- [0.5] Used `pydantic-settings` for config (already a FastAPI transitive dependency).
- [0.7] CI `actionlint` test replaced by a Python-based YAML parse test - `actionlint` is not installed locally; the test verifies the same constraints.
- [2.1] Using sha256 for session token hashing - simple, fast, sufficient for opaque tokens.
- [2.5] Rate limit counters use module-level singletons reset via conftest fixture between tests.
- [2.6] Using Tailwind CSS v4 with @tailwindcss/vite plugin - simpler than shadcn for now; will add shadcn components as needed.
- [2.6] Playwright e2e tests defined but run only via `make e2e` (need docker compose stack).

## Deviations from spec

Places where a spec file was changed because the code showed it was wrong or silent. Format: `- [phase.step] file, rule or section - what changed - why`.

- [0.1] CLAUDE.md references `docs/spec/` but files were in `docs/specs/` - renamed directory to match.

## Test and tool choices

- pytest 9.2.0 with `importlib` import mode (handles multiple `tests/` directories in workspace)
- Vitest 5.x with jsdom for frontend unit tests
- ruff 0.17.x for Python linting, oxlint for TypeScript/JS
- mypy 2.4.x in strict mode for Python type checking
- tsc with `strict: true` for TypeScript
- prometheus-client 0.26.x for metrics
- React Router v7 for frontend routing
- TanStack Query v5 for data fetching
- Tailwind CSS v4 for styling
- Playwright for e2e tests
