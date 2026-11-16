.PHONY: test check lint typecheck e2e evals smoke smoke-models

test:
	bash scripts/check.sh test

lint:
	bash scripts/check.sh lint

typecheck:
	bash scripts/check.sh typecheck

check:
	bash scripts/check.sh check

e2e:
	bash scripts/check.sh e2e

evals:
	bash scripts/check.sh evals

smoke:
	bash scripts/check.sh smoke

smoke-models:
	bash scripts/check.sh smoke-models
