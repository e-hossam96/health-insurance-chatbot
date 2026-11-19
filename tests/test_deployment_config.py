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
    assert "command" not in SERVICES["backend"], (
        "compose must not override the single-worker command"
    )
    backend_env = SERVICES["backend"].get("environment", {})
    assert (
        isinstance(backend_env, dict) and "PROMETHEUS_MULTIPROC_DIR" not in backend_env
    )
    assert "PROMETHEUS_MULTIPROC_DIR" not in dockerfile, (
        "prometheus_client stays in its default single-process mode"
    )


def test_H6_nginx_hides_metrics_and_proxies_the_api() -> None:
    nginx = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    blocked = re.search(r"location \^~ /api/metrics \{\s*return 404;\s*\}", nginx)
    assert blocked, "nginx must answer /api/metrics with 404"
    assert nginx.index("location ^~ /api/metrics") < nginx.index("location /api/")


def test_H6_only_nginx_is_public_and_grafana_needs_a_real_password() -> None:
    assert "ports" not in SERVICES["backend"]
    assert SERVICES["frontend"]["ports"] == ["80:8080"]
    for name in ("prometheus", "grafana"):
        ports = SERVICES[name]["ports"]
        assert isinstance(ports, list)
        assert all(str(p).startswith("127.0.0.1:") for p in ports), (
            f"{name} must bind to localhost only"
        )
    grafana_env = SERVICES["grafana"]["environment"]
    assert isinstance(grafana_env, dict)
    assert grafana_env["GF_SECURITY_ADMIN_PASSWORD"].startswith(
        "${GRAFANA_ADMIN_PASSWORD:?"
    )
    assert grafana_env["GF_AUTH_ANONYMOUS_ENABLED"] == "false"
    assert grafana_env["GF_USERS_ALLOW_SIGN_UP"] == "false"


def test_H1_H7_prometheus_keeps_15_days_on_a_volume_and_only_the_listed_services_run() -> (
    None
):
    prometheus = SERVICES["prometheus"]
    command = prometheus["command"]
    assert isinstance(command, list) and "--storage.tsdb.retention.time=15d" in command
    volumes = prometheus["volumes"]
    assert isinstance(volumes, list) and "prometheus_data:/prometheus" in volumes
    assert set(SERVICES) == {
        "postgres",
        "qdrant",
        "backend",
        "frontend",
        "prometheus",
        "grafana",
        "postgres-exporter",
    }


class _ComposeLoader(yaml.SafeLoader):
    pass


def _reset(loader: yaml.SafeLoader, node: yaml.Node) -> list[object]:
    return (
        list(loader.construct_sequence(node))
        if isinstance(node, yaml.SequenceNode)
        else []
    )


_ComposeLoader.add_constructor("!reset", _reset)
PROD = yaml.load(
    (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"),
    Loader=_ComposeLoader,
)
CADDYFILE = (ROOT / "Caddyfile").read_text(encoding="utf-8")
DEV_NGINX = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
CADDY_ADDRESS = "172.31.250.250"


def _networks_of(service: dict[str, object]) -> set[str]:
    networks = service.get("networks", [])
    return set(networks if isinstance(networks, list) else networks or {})


def test_F15_nginx_overwrites_the_forwarded_for_header_and_trusts_only_caddy() -> None:
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in DEV_NGINX
    assert "$proxy_add_x_forwarded_for" not in DEV_NGINX
    assert re.findall(r"set_real_ip_from (\S+);", DEV_NGINX) == [CADDY_ADDRESS]
    assert "real_ip_header X-Forwarded-For;" in DEV_NGINX
    assert "real_ip_recursive on;" not in DEV_NGINX
    caddy_networks = PROD["services"]["caddy"]["networks"]
    assert caddy_networks == {"edge": {"ipv4_address": CADDY_ADDRESS}}
    subnet = COMPOSE["networks"]["edge"]["ipam"]["config"][0]["subnet"]
    assert subnet == "172.31.250.0/24"


def test_H6_each_service_joins_only_the_networks_it_needs() -> None:
    expected = {
        "postgres": {"data"},
        "qdrant": {"data", "metrics"},
        "backend": {"app", "data", "metrics", "egress"},
        "frontend": {"edge", "app"},
        "prometheus": {"metrics"},
        "grafana": {"metrics"},
        "postgres-exporter": {"data", "metrics"},
    }
    assert {name: _networks_of(service) for name, service in SERVICES.items()} == expected
    assert COMPOSE["networks"]["app"]["internal"] is True, (
        "the frontend-to-backend network has no route out"
    )
    assert PROD["networks"]["data"]["internal"] is True, (
        "Postgres and Qdrant have no route out in production"
    )
    stack_test = yaml.safe_load(
        (ROOT / "docker-compose.stack-test.yml").read_text(encoding="utf-8")
    )
    assert _networks_of(stack_test["services"]["fakeai"]) == {"egress"}


def test_H6_production_caddy_is_the_only_public_service_and_serves_https() -> None:
    services = PROD["services"]
    assert services["caddy"]["ports"] == ["80:80", "443:443", "443:443/udp"]
    assert services["frontend"]["ports"] == []
    for name in ("postgres", "qdrant"):
        assert services[name]["ports"] == [], (
            f"{name} must not be published in production"
        )
    environment = services["caddy"]["environment"]
    assert environment["DOMAIN"].startswith("${DOMAIN:?")
    assert environment["LETSENCRYPT_EMAIL"].startswith("${LETSENCRYPT_EMAIL:?")
    assert "caddy_data:/data" in services["caddy"]["volumes"], (
        "certificates must survive a container rebuild"
    )
    assert "certbot" not in services
    site = CADDYFILE.split("{$DOMAIN} {", 1)[1]
    assert "email {$LETSENCRYPT_EMAIL}" in CADDYFILE
    assert re.search(r"reverse_proxy frontend:8080 \{\s*flush_interval -1\s*\}", site), (
        "Caddy must proxy to nginx and flush the chat stream at once"
    )
    assert 'Strict-Transport-Security "max-age=31536000"' in site
    assert "-Server" in site


def test_the_frontend_runs_nginx_as_a_non_root_user() -> None:
    dockerfile = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    runtime_image = re.findall(r"^FROM (\S+)", dockerfile, re.MULTILINE)[-1]
    assert runtime_image.startswith(("nginx:", "nginxinc/nginx-unprivileged:"))
    runtime_stage = dockerfile.split(f"FROM {runtime_image}", 1)[1]
    users = re.findall(r"^USER (\S+)", runtime_stage, re.MULTILINE)
    assert not any(user in {"root", "0"} for user in users)
    if runtime_image.startswith("nginx:"):
        assert users, "the official nginx image runs as root unless USER is set"
        assert "/tmp/nginx.pid" in runtime_stage, "a non-root nginx cannot write the default pid file"
    assert re.search(r"^\s*listen 8080;", DEV_NGINX, re.MULTILINE), (
        "a non-root nginx cannot bind port 80"
    )


def test_every_image_is_pinned_to_a_version() -> None:
    images = [
        s["image"]
        for s in {**SERVICES, **PROD["services"]}.values()
        if isinstance(s, dict) and "image" in s
    ]
    dockerfiles = [
        (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8"),
        (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8"),
    ]
    joined = "\n".join(dockerfiles)
    stages = set(re.findall(r"^FROM \S+ AS (\S+)", joined, re.MULTILINE))
    images += re.findall(r"^FROM (\S+)", joined, re.MULTILINE) + [
        i for i in re.findall(r"--from=(\S+)", joined) if i not in stages
    ]
    for image in images:
        tag = image.rsplit(":", 1)[-1] if ":" in image.split("/")[-1] else ""
        assert tag and tag != "latest", f"{image} is not pinned"


def test_F17_nginx_sends_a_content_security_policy_and_hides_its_version() -> None:
    policy = re.search(
        r'add_header Content-Security-Policy "([^"]+)" always;', DEV_NGINX
    )
    assert policy, "nginx must send a Content-Security-Policy"
    directives = dict(
        part.strip().split(" ", 1) for part in policy.group(1).split(";")
    )
    assert directives["script-src"] == "'self'", "no inline or remote scripts"
    assert (
        directives["object-src"] == "'none'"
        and directives["frame-ancestors"] == "'none'"
    )
    assert "server_tokens off;" in DEV_NGINX


def test_databases_are_local_only_in_development_and_need_a_real_password_in_production() -> (
    None
):
    for name, port in (("postgres", 5432), ("qdrant", 6333)):
        assert SERVICES[name]["ports"] == [f"127.0.0.1:{port}:{port}"], (
            f"{name} must bind to localhost only"
        )
    services = PROD["services"]
    for service, variable in (
        ("postgres", "POSTGRES_PASSWORD"),
        ("backend", "POSTGRES_PASSWORD"),
        ("postgres-exporter", "DATA_SOURCE_PASS"),
    ):
        assert services[service]["environment"][variable].startswith(
            "${POSTGRES_PASSWORD:?"
        ), f"{service} must refuse to start without a real password"
    assert "chatbot:chatbot@" not in (ROOT / "docker-compose.prod.yml").read_text(
        encoding="utf-8"
    )


def test_the_backend_runs_as_a_non_root_user() -> None:
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    users = re.findall(r"^USER (\S+)", dockerfile, re.MULTILINE)
    assert users and users[-1] not in {"root", "0"}
    assert dockerfile.index("USER app") < dockerfile.index("CMD")


def test_secrets_and_host_folders_stay_out_of_the_build_contexts() -> None:
    root_ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    frontend_ignore = (
        (ROOT / "frontend" / ".dockerignore").read_text(encoding="utf-8").splitlines()
    )
    assert (
        ".env" in root_ignore
        and "**/node_modules" in root_ignore
        and ".git" in root_ignore
    )
    assert ".env" in frontend_ignore and "node_modules" in frontend_ignore


def test_ci_reads_the_repo_only_and_pins_actions_to_commits() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert yaml.safe_load(workflow)["permissions"] == {"contents": "read"}
    for action in re.findall(r"uses: (\S+)", workflow):
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", action), (
            f"{action} is not pinned to a commit"
        )


def test_the_caddyfile_takes_the_domain_and_email_from_the_environment() -> None:
    assert "@" not in CADDYFILE, "the contact email belongs in .env, not in git"
    assert "hossammostafa" not in CADDYFILE
    assert not (ROOT / "scripts" / "issue_certificate.sh").exists()
    assert not (ROOT / "frontend" / "nginx.prod.conf.template").exists()
