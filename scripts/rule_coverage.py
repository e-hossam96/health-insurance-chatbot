#!/usr/bin/env python3

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml


def extract_rule_ids_from_rules(text: str) -> set[str]:
    return set(re.findall(r"\*\*([A-Z]\d+)\.\*\*", text))


def extract_rule_ids_from_schema(text: str) -> set[str]:
    return set(re.findall(r"//\s*([A-Z]\d+)\.", text))


def extract_all_rule_ids(
    rules_path: Path, schema_path: Path
) -> set[str]:
    ids: set[str] = set()
    if rules_path.exists():
        ids |= extract_rule_ids_from_rules(rules_path.read_text(encoding="utf-8"))
    if schema_path.exists():
        ids |= extract_rule_ids_from_schema(schema_path.read_text(encoding="utf-8"))
    return ids


def load_scope(scope_path: Path) -> dict[str, list[str]]:
    with scope_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_exemptions(exemptions_path: Path) -> set[str]:
    if not exemptions_path.exists():
        return set()
    text = exemptions_path.read_text(encoding="utf-8")
    return set(re.findall(r"^-\s+([A-Z]\d+)\s", text, re.MULTILINE))


def scan_test_files(test_dirs: list[Path]) -> set[str]:
    covered: set[str] = set()
    extensions = {"*.py", "*.ts", "*.tsx"}
    for d in test_dirs:
        if not d.exists():
            continue
        for ext in extensions:
            for f in d.rglob(ext):
                content = f.read_text(encoding="utf-8")
                covered |= set(re.findall(r"(?<![A-Za-z0-9])[A-Z]\d+(?![0-9])", content))
    return covered


def get_completed_phases(progress_path: Path) -> list[str]:
    if not progress_path.exists():
        return []
    text = progress_path.read_text(encoding="utf-8")
    return [
        f"phase_{m.group(1)}"
        for m in re.finditer(r"\|\s*(\d+)\s*\|[^|]*\|\s*done\s*\|", text)
    ]


def check_coverage(
    *,
    rules_path: Path,
    schema_path: Path,
    scope_path: Path,
    exemptions_path: Path,
    progress_path: Path,
    test_dirs: list[Path],
) -> list[str]:
    all_ids = extract_all_rule_ids(rules_path, schema_path)
    scope = load_scope(scope_path)
    exemptions = load_exemptions(exemptions_path)
    covered = scan_test_files(test_dirs)
    completed = get_completed_phases(progress_path)

    ids_in_scope: set[str] = set()
    for phase in completed:
        ids_in_scope |= set(scope.get(phase, []))

    unknown = ids_in_scope - all_ids
    missing = ids_in_scope - covered - exemptions

    errors: list[str] = []
    for uid in sorted(unknown):
        errors.append(f"unknown rule ID {uid} in scope")
    for mid in sorted(missing):
        errors.append(f"uncovered rule {mid} (no test or exemption)")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    errors = check_coverage(
        rules_path=root / "docs" / "spec" / "rules.md",
        schema_path=root / "docs" / "spec" / "schema.dbml",
        scope_path=root / "tests" / "rule_scope.yaml",
        exemptions_path=root / "tests" / "rule_coverage_exemptions.md",
        progress_path=root / "docs" / "progress.md",
        test_dirs=[
            root / "tests",
            root / "backend" / "tests",
            root / "packages" / "chatbot_ai" / "tests",
            root / "frontend" / "src",
            root / "frontend" / "e2e",
            root / "frontend" / "e2e-stack",
        ],
    )
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print("Rule coverage: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
