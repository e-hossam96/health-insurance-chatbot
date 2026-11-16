from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run_check(cmd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "scripts/check.sh", cmd],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )


def test_evals_prints_how_to_run_the_paid_suites() -> None:
    result = _run_check("evals")
    assert result.returncode == 0
    assert "cost money" in result.stdout
    assert "python -m chatbot_ai.evals" in result.stdout


def test_unknown_command_fails() -> None:
    result = _run_check("nonexistent")
    assert result.returncode != 0
