from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from prometheus_client import REGISTRY

import backend.metrics  # noqa: F401  # registers the backend metrics
from scripts.build_dashboards import DASHBOARD_DIR, render_all

ROOT = Path(__file__).resolve().parent.parent
OBSERVABILITY = ROOT / "observability"
EXPORTER_SERIES = {"up", "pg_up"}
PROMQL_WORDS = {"sum", "by", "rate", "increase", "histogram_quantile", "le", "route", "limit", "outcome", "agent", "stage", "kind", "action", "status", "job"}
METRIC_NAME = re.compile(r"\b([a-z_][a-z0-9_]*)\b")


def _backend_series() -> set[str]:
    # the registry has no public listing; its name index covers every series name
    return set(REGISTRY._names_to_collectors)


def test_H7_H8_committed_dashboards_match_the_generator() -> None:
    rendered = render_all()
    assert sorted(rendered) == ["api-health.json", "chat-llm.json", "demo-overview.json", "kb-ingestion.json"]
    for name, content in rendered.items():
        assert (DASHBOARD_DIR / name).read_text(encoding="utf-8") == content, f"{name} is stale: run scripts/build_dashboards.py"
    titles = {json.loads(content)["title"] for content in rendered.values()}
    assert titles == {"API health", "Chat and LLM", "KB ingestion", "Demo overview"}


def test_H8_every_dashboard_query_uses_a_metric_that_exists() -> None:
    known = _backend_series() | EXPORTER_SERIES
    for name, content in render_all().items():
        for panel in json.loads(content)["panels"]:
            assert panel["datasource"]["uid"] == "prometheus"
            for target in panel["targets"]:
                expr = re.sub(r'"[^"]*"|\[[^\]]*\]|\{\{[^}]*\}\}', " ", target["expr"])
                expr = re.sub(r"\{[^}]*\}", " ", expr)
                words = {w for w in METRIC_NAME.findall(expr) if not w.replace(".", "").isdigit()} - PROMQL_WORDS
                assert words, f"{name}: no metric in {target['expr']!r}"
                assert words <= known, f"{name}: unknown series {sorted(words - known)} in {target['expr']!r}"


def test_H1_prometheus_scrapes_backend_qdrant_and_postgres_every_15_s() -> None:
    config = yaml.safe_load((OBSERVABILITY / "prometheus.yml").read_text(encoding="utf-8"))
    assert config["global"]["scrape_interval"] == "15s"
    jobs = {job["job_name"]: job["static_configs"][0]["targets"] for job in config["scrape_configs"]}
    assert jobs == {"backend": ["backend:8000"], "qdrant": ["qdrant:6333"], "postgres": ["postgres-exporter:9187"]}
    assert "rule_files" not in config and "alerting" not in config
    assert all("scrape_interval" not in job for job in config["scrape_configs"]), "every job keeps the 15 s interval"


def test_H7_grafana_provisions_the_prometheus_datasource_and_the_dashboard_folder() -> None:
    datasource = yaml.safe_load((OBSERVABILITY / "grafana" / "provisioning" / "datasources" / "prometheus.yml").read_text(encoding="utf-8"))
    assert datasource["datasources"][0]["uid"] == "prometheus"
    assert datasource["datasources"][0]["url"] == "http://prometheus:9090"
    provider = yaml.safe_load((OBSERVABILITY / "grafana" / "provisioning" / "dashboards" / "dashboards.yml").read_text(encoding="utf-8"))
    assert provider["providers"][0]["options"]["path"] == "/var/lib/grafana/dashboards"


def test_H9_there_are_no_alert_rules() -> None:
    assert not list(OBSERVABILITY.rglob("*alert*"))
    assert not list(OBSERVABILITY.rglob("*rules*"))
    for content in render_all().values():
        assert all("alert" not in panel for panel in json.loads(content)["panels"])


REQUIRED_QUERIES = {
    "api-health": ("http_requests_total[", 'status=~"5..', "http_request_duration_seconds_bucket", "rate_limit_rejections_total"),
    "chat-llm": (
        "chat_turns_total",
        "chat_turns_by_agent_total",
        "chat_ttft_seconds_bucket",
        "chat_llm_duration_seconds_bucket",
        "chat_stage_duration_seconds_bucket",
        "chat_chunk_gap_seconds_bucket",
        "chat_tokens_total",
    ),
    "kb-ingestion": ("kb_documents_processing", "kb_ingest_total", "kb_ingest_duration_seconds_bucket"),
    "demo-overview": ("signups_total", 'action="book",outcome="ok"', 'action="cancel",outcome="ok"', 'action="complaint",outcome="ok"', "chat_turns_total"),
}
LABEL_VALUES = {"action": {"book", "cancel", "complaint"}, "outcome": {"ok", "error", "cancelled", "failed", "conflict", "rejected"}, "job": {"qdrant", "backend", "postgres"}}


def test_H8_each_dashboard_shows_what_it_is_for_with_real_label_values() -> None:
    for uid, required in REQUIRED_QUERIES.items():
        exprs = " ".join(t["expr"] for p in json.loads(render_all()[f"{uid}.json"])["panels"] for t in p["targets"])
        for fragment in required:
            assert fragment in exprs, f"{uid} is missing {fragment!r}"
        for key, value in re.findall(r'(\w+)="([^"]*)"', exprs):
            if key in LABEL_VALUES:
                assert value in LABEL_VALUES[key], f"{uid}: {key}={value!r} is not a real label value"
