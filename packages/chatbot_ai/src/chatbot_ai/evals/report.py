from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from chatbot_ai.settings import AISettings, Role

SWITCHES = (
    "ai_query_count",
    "ai_retrieval_mode",
    "ai_prefetch_k",
    "ai_fused_k",
    "ai_context_k",
    "ai_rerank_provider",
    "ai_rerank_min_score",
    "ai_router_history_rows",
    "ai_chat_max_output_tokens",
)


def config_snapshot(settings: AISettings) -> dict[str, object]:
    roles = {
        role.value: {
            "base_url": getattr(settings, f"ai_{role.value}_base_url"),
            "model": getattr(settings, f"ai_{role.value}_model"),
        }
        for role in Role
    }
    return {"roles": roles, "switches": {name: getattr(settings, name) for name in SWITCHES}}


def write_report(
    suite: str, result: BaseModel, settings: AISettings, now: datetime, out_dir: Path
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "suite": suite,
        "date": now.isoformat(),
        "config": config_snapshot(settings),
        "result": result.model_dump(mode="json"),
    }
    json_path = out_dir / f"{suite}-{stamp}.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [f"# {suite} eval, {now.isoformat()}", "", "## Config", "", "```json", json.dumps(payload["config"], indent=2), "```", "", "## Result", ""]
    for key, value in result.model_dump(mode="json").items():
        if isinstance(value, (dict, list)):
            lines += [f"### {key}", "", "```json", json.dumps(value, indent=2), "```", ""]
        else:
            lines.append(f"- {key}: {value}")
    md_path = out_dir / f"{suite}-{stamp}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path
