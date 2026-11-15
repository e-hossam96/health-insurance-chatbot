"""Tests for the CI workflow configuration."""

from __future__ import annotations

from pathlib import Path

import yaml


def _load_workflow() -> dict:  # type: ignore[type-arg]
    path = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)  # type: ignore[no-any-return]


def test_only_trigger_is_push_to_main() -> None:
    wf = _load_workflow()
    triggers = wf.get("on") or wf.get(True)
    assert triggers is not None
    assert list(triggers.keys()) == ["push"]
    assert triggers["push"]["branches"] == ["main"]


def test_no_job_runs_evals() -> None:
    wf = _load_workflow()
    for job_name, job in wf["jobs"].items():
        for step in job.get("steps", []):
            run_cmd = step.get("run", "")
            assert "make evals" not in run_cmd, (
                f"Job {job_name} runs evals"
            )
