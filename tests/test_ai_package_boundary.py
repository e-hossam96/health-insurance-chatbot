from __future__ import annotations

import ast
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "packages" / "chatbot_ai"
FORBIDDEN = ("prometheus", "fastapi", "starlette", "sqlalchemy", "asyncpg", "psycopg", "backend")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def test_H2_the_ai_package_declares_no_prometheus_web_or_database_dependency() -> None:
    project = tomllib.loads((PACKAGE / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = [d.lower() for d in project["project"]["dependencies"]]
    assert not [d for d in dependencies if d.startswith(FORBIDDEN)], dependencies


def test_H2_the_ai_package_imports_no_prometheus_web_or_database_module() -> None:
    offenders = {
        f"{path.relative_to(PACKAGE)}: {module}"
        for path in (PACKAGE / "src" / "chatbot_ai").rglob("*.py")
        for module in _imported_modules(path)
        if module.split(".")[0].startswith(FORBIDDEN)
    }
    assert offenders == set()


def test_H2_importing_the_ai_package_does_not_load_prometheus_client() -> None:
    probe = "import sys, chatbot_ai, chatbot_ai.orchestrator, chatbot_ai.ingest; print('prometheus_client' in sys.modules)"
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True, cwd=ROOT)
    assert result.stdout.strip() == "False"
