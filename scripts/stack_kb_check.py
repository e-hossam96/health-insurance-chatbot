from __future__ import annotations

import http.client
import json
import os
import sys
import time
import uuid

HOST = "localhost"
PORT = 80
TIMEOUT_S = 180
DOCUMENT = (
    "Outpatient care. Specialist visits at network clinics have a co-pay of 50 EGP per visit.\n\n"
    "Exclusions. Cosmetic treatment is not covered.\n"
)


def _request(
    method: str, path: str, body: bytes | None, headers: dict[str, str]
) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection(HOST, PORT, timeout=30)
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    result = (
        response.status,
        {k.lower(): v for k, v in response.getheaders()},
        response.read(),
    )
    connection.close()
    return result


def main() -> int:
    username = os.environ["SMOKE_ADMIN"]
    login = json.dumps({"username": username, "password": "adminpass1"}).encode()
    status, headers, body = _request(
        "POST", "/api/auth/login", login, {"Content-Type": "application/json"}
    )
    if status != 200:
        raise SystemExit(f"FAIL: admin login returned {status}: {body!r}")
    cookie = headers.get("set-cookie", "").split(";", 1)[0]

    filename = f"smoke-{uuid.uuid4().hex[:8]}.txt"
    status, _, body = _request(
        "POST",
        f"/api/admin/kb-documents?filename={filename}",
        DOCUMENT.encode(),
        {"Content-Type": "text/plain", "Cookie": cookie},
    )
    if status != 201:
        raise SystemExit(f"FAIL: the KB upload returned {status}: {body!r}")
    document_id = json.loads(body)["id"]

    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        status, _, body = _request(
            "GET", "/api/admin/kb-documents?limit=50&offset=0", None, {"Cookie": cookie}
        )
        item = next(i for i in json.loads(body)["items"] if i["id"] == document_id)
        if item["status"] == "ready":
            print("OK: a KB document was stored and ingested by the non-root backend")
            return 0
        if item["status"] == "failed":
            raise SystemExit(f"FAIL: ingestion failed: {item['error_message']}")
        time.sleep(1)
    raise SystemExit(f"FAIL: the KB document was not ready after {TIMEOUT_S} s")


if __name__ == "__main__":
    sys.exit(main())
