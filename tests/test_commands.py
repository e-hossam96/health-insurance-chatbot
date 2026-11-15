"""Tests for the command runner (scripts/check.sh)."""

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


def test_evals_prints_not_available() -> None:
    result = _run_check("evals")
    assert result.returncode == 0
    assert "Not available before phase 6" in result.stdout


def test_unknown_command_fails() -> None:
    result = _run_check("nonexistent")
    assert result.returncode != 0
