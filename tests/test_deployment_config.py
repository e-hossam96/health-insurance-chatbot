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
    assert "uvicorn" in command and re.search(r"--workers\s+1(?!\d)", command)
    assert "command" not in SERVICES["backend"], "compose must not override the single-worker command"
    backend_env = SERVICES["backend"].get("environment", {})
    assert isinstance(backend_env, dict) and "PROMETHEUS_MULTIPROC_DIR" not in backend_env
    assert "PROMETHEUS_MULTIPROC_DIR" not in dockerfile, "prometheus_client stays in its default single-process mode"


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


class _ComposeLoader(yaml.SafeLoader):
    pass


def _reset(loader: yaml.SafeLoader, node: yaml.Node) -> list[object]:
    return list(loader.construct_sequence(node)) if isinstance(node, yaml.SequenceNode) else []


_ComposeLoader.add_constructor("!reset", _reset)
PROD = yaml.load((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"), Loader=_ComposeLoader)
PROD_NGINX = (ROOT / "frontend" / "nginx.prod.conf.template").read_text(encoding="utf-8")


def test_F15_nginx_overwrites_the_forwarded_for_header() -> None:
    for config in ((ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8"), PROD_NGINX):
        assert "proxy_set_header X-Forwarded-For $remote_addr;" in config
        assert "$proxy_add_x_forwarded_for" not in config


def test_H6_production_nginx_serves_https_only_and_keeps_metrics_private() -> None:
    http_block, https_block = PROD_NGINX.split("listen 443 ssl;")
    assert "location /.well-known/acme-challenge/" in http_block
    assert "return 301 https://$host$request_uri;" in http_block
    assert "ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;" in https_block
    assert "Strict-Transport-Security" in https_block
    assert re.search(r"location \^~ /api/metrics \{\s*return 404;\s*\}", https_block)
    assert "proxy_buffering off;" in https_block


def test_production_compose_publishes_only_80_and_443_and_renews_certificates() -> None:
    services = PROD["services"]
    assert services["frontend"]["ports"] == ["80:80", "443:443"]
    assert services["frontend"]["environment"]["DOMAIN"].startswith("${DOMAIN:?")
    assert "certbot renew" in " ".join(services["certbot"]["entrypoint"])
    for name in ("postgres", "qdrant"):
        assert services[name]["ports"] == [], f"{name} must not be published in production"


def test_every_image_is_pinned_to_a_version() -> None:
    images = [s["image"] for s in {**SERVICES, **PROD["services"]}.values() if isinstance(s, dict) and "image" in s]
    dockerfiles = [(ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8"), (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")]
    joined = "\n".join(dockerfiles)
    stages = set(re.findall(r"^FROM \S+ AS (\S+)", joined, re.MULTILINE))
    images += re.findall(r"^FROM (\S+)", joined, re.MULTILINE) + [i for i in re.findall(r"--from=(\S+)", joined) if i not in stages]
    for image in images:
        tag = image.rsplit(":", 1)[-1] if ":" in image.split("/")[-1] else ""
        assert tag and tag != "latest", f"{image} is not pinned"
