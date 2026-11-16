from __future__ import annotations

import http.client
import json
import sys
import time
import uuid

HOST = "localhost"
PORT = 80
TOKEN_DELAY_S = 0.3
MIN_TOKENS = 5


def _request(method: str, path: str, body: dict[str, object] | None, cookie: str | None) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection(HOST, PORT, timeout=30)
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
    response = connection.getresponse()
    payload = response.read()
    result = response.status, {k.lower(): v for k, v in response.getheaders()}, payload
    connection.close()
    return result


def _session_cookie(headers: dict[str, str]) -> str:
    raw = headers.get("set-cookie", "")
    cookie = raw.split(";", 1)[0]
    if not cookie.startswith("session_id="):
        raise SystemExit(f"FAIL: login did not set the session cookie ({raw!r})")
    return cookie


def main() -> int:
    username = f"stack{uuid.uuid4().hex[:8]}"
    status, _, body = _request("POST", "/api/auth/signup", {"username": username, "password": "stackpass1"}, None)
    if status != 201:
        raise SystemExit(f"FAIL: signup returned {status}: {body!r}")
    status, headers, _ = _request("POST", "/api/auth/login", {"username": username, "password": "stackpass1"}, None)
    cookie = _session_cookie(headers)
    status, _, body = _request("GET", "/api/locations", None, cookie)
    locations = json.loads(body)
    if not locations:
        raise SystemExit("FAIL: no locations; the stack needs a seeded location")
    status, _, body = _request("POST", "/api/me/profile", {"name": "Stack Test", "location_id": locations[0]["id"]}, cookie)
    if status not in (200, 201):
        raise SystemExit(f"FAIL: profile returned {status}: {body!r}")

    connection = http.client.HTTPConnection(HOST, PORT, timeout=60)
    started = time.monotonic()
    connection.request("POST", "/api/me/chat", body=json.dumps({"message": "hello"}), headers={"Content-Type": "application/json", "Cookie": cookie})
    response = connection.getresponse()
    if response.status != 200:
        raise SystemExit(f"FAIL: chat returned {response.status}: {response.read()!r}")
    arrivals: list[float] = []
    events: list[str] = []
    while True:
        line = response.fp.readline()
        if not line:
            break
        text = line.decode("utf-8").rstrip("\r\n")
        if text.startswith("event: "):
            events.append(text.removeprefix("event: "))
            if events[-1] == "token":
                arrivals.append(time.monotonic() - started)
            if events[-1] in ("done", "error"):
                break
    connection.close()

    print(f"events: {events[:3]}...{events[-2:]}, tokens: {len(arrivals)}, first at {arrivals[0] if arrivals else -1:.2f}s, last at {arrivals[-1] if arrivals else -1:.2f}s")
    if "done" not in events:
        raise SystemExit(f"FAIL: the turn did not finish: {events}")
    if len(arrivals) < MIN_TOKENS:
        raise SystemExit(f"FAIL: expected at least {MIN_TOKENS} token events, got {len(arrivals)}")
    spread = arrivals[-1] - arrivals[0]
    if spread < TOKEN_DELAY_S * (len(arrivals) - 2):
        raise SystemExit(f"FAIL: tokens arrived together ({spread:.2f}s spread); nginx is buffering the stream")
    print("OK: tokens streamed through nginx one by one")

    victim = f"victim{uuid.uuid4().hex[:8]}"
    _request("POST", "/api/auth/signup", {"username": victim, "password": "victimpass1"}, None)
    statuses = []
    for attempt in range(11):
        connection = http.client.HTTPConnection(HOST, PORT, timeout=30)
        connection.request(
            "POST",
            "/api/auth/login",
            body=json.dumps({"username": victim, "password": "wrong-password"}),
            headers={"Content-Type": "application/json", "X-Forwarded-For": f"203.0.113.{attempt}"},
        )
        statuses.append(connection.getresponse().status)
        connection.close()
    if statuses[-1] != 429:
        raise SystemExit(f"FAIL: spoofed X-Forwarded-For headers escaped the login limit: {statuses}")
    print("OK: a spoofed X-Forwarded-For header does not escape the login rate limit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
