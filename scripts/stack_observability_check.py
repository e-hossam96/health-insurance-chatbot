from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROMETHEUS = "http://127.0.0.1:9090"
GRAFANA = "http://127.0.0.1:3000"
EXPECTED_JOBS = {"backend", "qdrant", "postgres"}
EXPECTED_DASHBOARDS = {"api-health", "chat-llm", "kb-ingestion", "demo-overview"}
TARGET_DEADLINE_S = 120.0
DASHBOARDS = Path(__file__).resolve().parent.parent / "observability" / "grafana" / "dashboards"


def _get(url: str, headers: dict[str, str] | None = None) -> object:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def _targets() -> dict[str, str]:
    payload = _get(f"{PROMETHEUS}/api/v1/targets")
    assert isinstance(payload, dict)
    return {t["labels"]["job"]: t["health"] for t in payload["data"]["activeTargets"]}


def main() -> int:
    give_up = time.monotonic() + TARGET_DEADLINE_S
    health = _targets()
    while set(health) != EXPECTED_JOBS or any(state != "up" for state in health.values()):
        if time.monotonic() > give_up:
            raise SystemExit(f"FAIL: Prometheus targets not all up: {health}")
        time.sleep(3)
        health = _targets()
    print(f"OK: Prometheus targets up: {sorted(health)}")

    flags = _get(f"{PROMETHEUS}/api/v1/status/flags")
    assert isinstance(flags, dict)
    retention = flags["data"]["storage.tsdb.retention.time"]
    if retention != "15d":
        raise SystemExit(f"FAIL: retention is {retention}, expected 15d")
    print("OK: Prometheus retention is 15d")

    token = base64.b64encode(f"admin:{os.environ['GRAFANA_ADMIN_PASSWORD']}".encode()).decode()
    dashboards = _get(f"{GRAFANA}/api/search?type=dash-db", {"Authorization": f"Basic {token}"})
    assert isinstance(dashboards, list)
    uids = {d["uid"] for d in dashboards}
    if not EXPECTED_DASHBOARDS <= uids:
        raise SystemExit(f"FAIL: Grafana dashboards {sorted(uids)}, expected {sorted(EXPECTED_DASHBOARDS)}")
    print(f"OK: Grafana lists the dashboards {sorted(EXPECTED_DASHBOARDS)}")

    default_login = base64.b64encode(b"admin:admin").decode()
    for label, headers in (("anonymous access", {}), ("the default admin:admin login", {"Authorization": f"Basic {default_login}"})):
        try:
            _get(f"{GRAFANA}/api/search?type=dash-db", headers)
        except urllib.error.HTTPError as error:
            if error.code != 401:
                raise
            print(f"OK: Grafana refuses {label}")
        else:
            raise SystemExit(f"FAIL: Grafana accepted {label}")

    give_up = time.monotonic() + TARGET_DEADLINE_S
    while not all(_has_series(name) for name in ("chat_turns_total", "signups_total")):
        if time.monotonic() > give_up:
            raise SystemExit("FAIL: Prometheus has no chat_turns_total or signups_total series from the backend")
        time.sleep(3)
    print("OK: Prometheus ingested the backend's chat and sign-up series")

    for path in sorted(DASHBOARDS.glob("*.json")):
        for panel in json.loads(path.read_text(encoding="utf-8"))["panels"]:
            for target in panel["targets"]:
                result = _get(f"{PROMETHEUS}/api/v1/query?" + urllib.parse.urlencode({"query": target["expr"]}))
                assert isinstance(result, dict)
                if result.get("status") != "success":
                    raise SystemExit(f"FAIL: {path.name} panel {panel['title']!r} query failed: {result}")
    print("OK: every dashboard query runs on Prometheus")
    return 0


def _has_series(name: str) -> bool:
    result = _get(f"{PROMETHEUS}/api/v1/query?" + urllib.parse.urlencode({"query": name}))
    assert isinstance(result, dict)
    return bool(result["data"]["result"])


if __name__ == "__main__":
    sys.exit(main())
