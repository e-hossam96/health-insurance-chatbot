from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
from scripts.rule_coverage import (
    check_coverage,
    extract_all_rule_ids,
    extract_rule_ids_from_rules,
    extract_rule_ids_from_schema,
    load_exemptions,
    scan_test_files,
)


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    (tmp_path / "rules.md").write_text(
        dedent("""\
        ## B. Accounts
        - **B1.** Sign-up is users only.
        - **B2.** Admin profiles created in DB.
        ## C. Slots
        - **C1.** One hour, on the hour.
        """),
        encoding="utf-8",
    )
    (tmp_path / "schema.dbml").write_text(
        dedent("""\
        // A1. slot on the hour
        // A2. One active visit per slot
        """),
        encoding="utf-8",
    )
    (tmp_path / "scope.yaml").write_text(
        dedent("""\
        phase_0: []
        phase_1:
          - A1
          - A2
          - B1
        phase_2:
          - C1
        """),
        encoding="utf-8",
    )
    (tmp_path / "exemptions.md").write_text("", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    return tmp_path


def test_extract_from_rules() -> None:
    text = "- **B1.** foo\n- **C3.** bar\n"
    assert extract_rule_ids_from_rules(text) == {"B1", "C3"}


def test_extract_from_schema() -> None:
    text = "// A1. on the hour\n// A2. unique\n"
    assert extract_rule_ids_from_schema(text) == {"A1", "A2"}


def test_all_ids(tmp_project: Path) -> None:
    ids = extract_all_rule_ids(
        tmp_project / "rules.md", tmp_project / "schema.dbml"
    )
    assert ids == {"A1", "A2", "B1", "B2", "C1"}


def test_covered_ids(tmp_project: Path) -> None:
    test_dir = tmp_project / "tests"
    (test_dir / "test_a.py").write_text(
        "def test_A1_slot_on_hour(): pass\n", encoding="utf-8"
    )
    covered = scan_test_files([test_dir])
    assert "A1" in covered


def test_no_completed_phases_passes(tmp_project: Path) -> None:
    progress = tmp_project / "progress.md"
    progress.write_text("| 1 | Data model | not started | - |", encoding="utf-8")
    errors = check_coverage(
        rules_path=tmp_project / "rules.md",
        schema_path=tmp_project / "schema.dbml",
        scope_path=tmp_project / "scope.yaml",
        exemptions_path=tmp_project / "exemptions.md",
        progress_path=progress,
        test_dirs=[tmp_project / "tests"],
    )
    assert errors == []


def test_completed_phase_uncovered(tmp_project: Path) -> None:
    progress = tmp_project / "progress.md"
    progress.write_text("| 1 | Data model | done | 1.3 |", encoding="utf-8")
    errors = check_coverage(
        rules_path=tmp_project / "rules.md",
        schema_path=tmp_project / "schema.dbml",
        scope_path=tmp_project / "scope.yaml",
        exemptions_path=tmp_project / "exemptions.md",
        progress_path=progress,
        test_dirs=[tmp_project / "tests"],
    )
    assert "uncovered rule A1" in errors[0]
    assert any("A2" in e for e in errors)
    assert any("B1" in e for e in errors)


def test_completed_phase_covered(tmp_project: Path) -> None:
    progress = tmp_project / "progress.md"
    progress.write_text("| 1 | Data model | done | 1.3 |", encoding="utf-8")
    test_dir = tmp_project / "tests"
    (test_dir / "test_all.py").write_text(
        dedent("""\
        def test_A1_x(): pass
        def test_A2_y(): pass
        def test_B1_z(): pass
        """),
        encoding="utf-8",
    )
    errors = check_coverage(
        rules_path=tmp_project / "rules.md",
        schema_path=tmp_project / "schema.dbml",
        scope_path=tmp_project / "scope.yaml",
        exemptions_path=tmp_project / "exemptions.md",
        progress_path=progress,
        test_dirs=[tmp_project / "tests"],
    )
    assert errors == []


def test_exempted_rule_not_flagged(tmp_project: Path) -> None:
    progress = tmp_project / "progress.md"
    progress.write_text("| 1 | Data model | done | 1.3 |", encoding="utf-8")
    test_dir = tmp_project / "tests"
    (test_dir / "test_partial.py").write_text(
        "def test_A1_x(): pass\ndef test_A2_y(): pass\n", encoding="utf-8"
    )
    exemptions = tmp_project / "exemptions.md"
    exemptions.write_text("- B1 - tested via integration\n", encoding="utf-8")
    errors = check_coverage(
        rules_path=tmp_project / "rules.md",
        schema_path=tmp_project / "schema.dbml",
        scope_path=tmp_project / "scope.yaml",
        exemptions_path=exemptions,
        progress_path=progress,
        test_dirs=[tmp_project / "tests"],
    )
    assert errors == []


def test_unknown_id_in_scope(tmp_project: Path) -> None:
    progress = tmp_project / "progress.md"
    progress.write_text("| 1 | Data model | done | 1.3 |", encoding="utf-8")
    scope = tmp_project / "scope.yaml"
    scope.write_text("phase_1:\n  - Z99\n", encoding="utf-8")
    errors = check_coverage(
        rules_path=tmp_project / "rules.md",
        schema_path=tmp_project / "schema.dbml",
        scope_path=scope,
        exemptions_path=tmp_project / "exemptions.md",
        progress_path=progress,
        test_dirs=[tmp_project / "tests"],
    )
    assert any("unknown rule ID Z99" in e for e in errors)


def test_load_exemptions_format(tmp_path: Path) -> None:
    exemptions = tmp_path / "exemptions.md"
    exemptions.write_text("- A1 - reason one\n- B2 - reason two\n", encoding="utf-8")
    result = load_exemptions(exemptions)
    assert result == {"A1", "B2"}
