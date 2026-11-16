from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
SERVICES: dict[str, dict[str, object]] = COMPOSE["services"]


def test_H5_the_backend_runs_one_uvicorn_worker() -> None:
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    command = next(line for line in dockerfile.splitlines() if line.startswith("CMD"))
    assert "uvicorn" in command and "--workers 1" in command
    assert "command" not in SERVICES["backend"], "compose must not override the single-worker command"


def test_H6_nginx_hides_metrics_and_proxies_the_api() -> None:
    nginx = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    blocked = re.search(r"location \^~ /api/metrics \{\s*return 404;\s*\}", nginx)
    assert blocked, "nginx must answer /api/metrics with 404"
    assert nginx.index("location ^~ /api/metrics") < nginx.index("location /api/")


def test_H6_only_nginx_is_public_and_grafana_needs_a_real_password() -> None:
    assert "ports" not in SERVICES["backend"]
    assert SERVICES["frontend"]["ports"] == ["80:80"]
    for name in ("prometheus", "grafana"):
        ports = SERVICES[name]["ports"]
        assert isinstance(ports, list)
        assert all(str(p).startswith("127.0.0.1:") for p in ports), f"{name} must bind to localhost only"
    grafana_env = SERVICES["grafana"]["environment"]
    assert isinstance(grafana_env, dict)
    assert grafana_env["GF_SECURITY_ADMIN_PASSWORD"].startswith("${GRAFANA_ADMIN_PASSWORD:?")
    assert grafana_env["GF_AUTH_ANONYMOUS_ENABLED"] == "false"
    assert grafana_env["GF_USERS_ALLOW_SIGN_UP"] == "false"


def test_H1_H7_prometheus_keeps_15_days_on_a_volume_and_only_the_listed_services_run() -> None:
    prometheus = SERVICES["prometheus"]
    command = prometheus["command"]
    assert isinstance(command, list) and "--storage.tsdb.retention.time=15d" in command
    volumes = prometheus["volumes"]
    assert isinstance(volumes, list) and "prometheus_data:/prometheus" in volumes
    assert set(SERVICES) == {"postgres", "qdrant", "backend", "frontend", "prometheus", "grafana", "postgres-exporter"}
