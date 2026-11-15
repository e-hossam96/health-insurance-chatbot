from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from chatbot_ai.clients import RoleClients
from chatbot_ai.evals.report import write_report
from chatbot_ai.evals.routing import load_routing, run_routing
from chatbot_ai.settings import AISettings, Role

EVALS_DIR = Path(__file__).resolve().parent
DATASETS_DIR = EVALS_DIR / "datasets"
REPORTS_DIR = EVALS_DIR / "reports"
SUITES = ("ingest", "routing", "retrieval", "answers", "tools")
IMPLEMENTED = ("routing",)
SMOKE_ITEMS = 5


class EvalUsageError(ValueError):
    pass


def parse_overrides(pairs: Sequence[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for pair in pairs:
        key, separator, value = pair.partition("=")
        if not separator or not key:
            raise EvalUsageError(f"--set expects KEY=VALUE, got {pair!r}")
        overrides[key.strip().lower()] = value
    return overrides


def build_settings(overrides: dict[str, str]) -> AISettings:
    unknown = sorted(set(overrides) - set(AISettings.model_fields))
    if unknown:
        raise EvalUsageError(f"unknown setting(s): {', '.join(unknown)}")
    return AISettings(**overrides)  # type: ignore[arg-type]  # --set values are strings that pydantic coerces


async def run_suite(suite: str, settings: AISettings, smoke: bool, out_dir: Path, now: datetime) -> list[Path]:
    if suite not in IMPLEMENTED:
        raise EvalUsageError(f"the {suite} suite is not implemented yet")
    clients = RoleClients(settings)
    try:
        items = load_routing(DATASETS_DIR / "routing.jsonl")
        if smoke:
            items = items[:SMOKE_ITEMS]
        report = await run_routing(items, clients.get(Role.router), settings.ai_router_history_rows)
    finally:
        await clients.aclose()
    return list(write_report(suite, report, settings, now, out_dir))


def main(argv: Sequence[str] | None = None, out_dir: Path = REPORTS_DIR) -> int:
    parser = argparse.ArgumentParser(prog="python -m chatbot_ai.evals")
    parser.add_argument("suite", choices=(*SUITES, "all"))
    parser.add_argument("--set", dest="overrides", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--langfuse", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.langfuse:
            raise EvalUsageError("--langfuse arrives with the Langfuse step (7.4)")
        settings = build_settings(parse_overrides(args.overrides))
        suites = IMPLEMENTED if args.suite == "all" else (args.suite,)
        now = datetime.now(UTC)
        for suite in suites:
            for path in asyncio.run(run_suite(suite, settings, args.smoke, out_dir, now)):
                print(path)
    except EvalUsageError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
