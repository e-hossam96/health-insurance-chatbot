from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = ROOT / "observability" / "grafana" / "dashboards"
DATASOURCE = {"type": "prometheus", "uid": "prometheus"}


@dataclass(frozen=True)
class Panel:
    title: str
    exprs: tuple[tuple[str, str], ...]
    unit: str = "short"
    kind: str = "timeseries"


@dataclass(frozen=True)
class Dashboard:
    uid: str
    title: str
    panels: tuple[Panel, ...]


def p95(metric: str, by: str = "") -> str:
    group = f"le, {by}" if by else "le"
    return f"histogram_quantile(0.95, sum by ({group}) (rate({metric}_bucket[5m])))"


DASHBOARDS = (
    Dashboard(
        "api-health",
        "API health",
        (
            Panel("Requests per second by route", (("sum by (route) (rate(http_requests_total[5m]))", "{{route}}"),), "reqps"),
            Panel("5xx errors per second", (('sum by (route) (rate(http_requests_total{status=~"5.."}[5m]))', "{{route}}"),), "reqps"),
            Panel("p95 latency by route", ((p95("http_request_duration_seconds", "route"), "{{route}}"),), "s"),
            Panel("Rate-limit rejections", (("sum by (limit) (increase(rate_limit_rejections_total[1h]))", "{{limit}}"),)),
            Panel("Postgres up", (("pg_up", "postgres"),), kind="stat"),
        ),
    ),
    Dashboard(
        "chat-llm",
        "Chat and LLM",
        (
            Panel("Turns by outcome", (("sum by (outcome) (increase(chat_turns_total[1h]))", "{{outcome}}"),)),
            Panel("Turns by agent", (("sum by (agent) (increase(chat_turns_by_agent_total[1h]))", "{{agent}}"),)),
            Panel(
                "Time to first token",
                (
                    ("histogram_quantile(0.5, sum by (le) (rate(chat_ttft_seconds_bucket[5m])))", "p50"),
                    (p95("chat_ttft_seconds"), "p95"),
                ),
                "s",
            ),
            Panel("LLM and turn duration p95", ((p95("chat_llm_duration_seconds"), "llm"), (p95("chat_turn_duration_seconds"), "turn")), "s"),
            Panel("Stage duration p95", ((p95("chat_stage_duration_seconds", "stage"), "{{stage}}"),), "s"),
            Panel("Chunk gap p95", ((p95("chat_chunk_gap_seconds"), "gap"),), "s"),
            Panel("Tokens per hour", (("sum by (kind) (increase(chat_tokens_total[1h]))", "{{kind}}"),)),
        ),
    ),
    Dashboard(
        "kb-ingestion",
        "KB ingestion",
        (
            Panel("Documents processing", (("kb_documents_processing", "processing"),), kind="stat"),
            Panel("Ingestion outcomes", (("sum by (outcome) (increase(kb_ingest_total[1h]))", "{{outcome}}"),)),
            Panel("Ingestion duration p95", ((p95("kb_ingest_duration_seconds"), "p95"),), "s"),
            Panel("Qdrant up", (('up{job="qdrant"}', "qdrant"),), kind="stat"),
        ),
    ),
    Dashboard(
        "demo-overview",
        "Demo overview",
        (
            Panel("Sign-ups (24 h)", (("sum(increase(signups_total[24h]))", "signups"),), kind="stat"),
            Panel("Bookings (24 h)", (('sum(increase(card_actions_total{action="book",outcome="ok"}[24h]))', "bookings"),), kind="stat"),
            Panel("Cancellations (24 h)", (('sum(increase(card_actions_total{action="cancel",outcome="ok"}[24h]))', "cancellations"),), kind="stat"),
            Panel("Complaints (24 h)", (('sum(increase(card_actions_total{action="complaint",outcome="ok"}[24h]))', "complaints"),), kind="stat"),
            Panel("Chat turns (24 h)", (("sum(increase(chat_turns_total[24h]))", "turns"),), kind="stat"),
            Panel("Card actions by outcome", (("sum by (action, outcome) (increase(card_actions_total[1h]))", "{{action}} {{outcome}}"),)),
        ),
    ),
)


def render(dashboard: Dashboard) -> dict[str, object]:
    panels: list[dict[str, object]] = []
    for index, panel in enumerate(dashboard.panels):
        width = 6 if panel.kind == "stat" else 12
        per_row = 24 // width
        panels.append(
            {
                "id": index + 1,
                "type": panel.kind,
                "title": panel.title,
                "datasource": DATASOURCE,
                "gridPos": {"x": (index % per_row) * width, "y": (index // per_row) * 8, "w": width, "h": 8},
                "fieldConfig": {"defaults": {"unit": panel.unit}, "overrides": []},
                "options": {},
                "targets": [
                    {"refId": chr(ord("A") + n), "datasource": DATASOURCE, "expr": expr, "legendFormat": legend}
                    for n, (expr, legend) in enumerate(panel.exprs)
                ],
            }
        )
    return {
        "uid": dashboard.uid,
        "title": dashboard.title,
        "schemaVersion": 39,
        "version": 1,
        "editable": False,
        "time": {"from": "now-6h", "to": "now"},
        "refresh": "30s",
        "tags": ["health-assistant"],
        "panels": panels,
    }


def render_all() -> dict[str, str]:
    return {f"{d.uid}.json": json.dumps(render(d), indent=2) + "\n" for d in DASHBOARDS}


def main() -> int:
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in render_all().items():
        (DASHBOARD_DIR / name).write_text(content, encoding="utf-8", newline="\n")
        print(DASHBOARD_DIR / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
