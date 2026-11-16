from __future__ import annotations

import re
from pathlib import Path

NGINX_CONF = Path(__file__).resolve().parent.parent / "frontend" / "nginx.conf"
KB_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
UNITS = {"": 1, "k": 1024, "m": 1024 * 1024, "g": 1024 * 1024 * 1024}


def test_G2_nginx_caps_the_body_just_above_the_upload_limit() -> None:
    match = re.search(r"^\s*client_max_body_size\s+(\d+)([kmg]?)\s*;", NGINX_CONF.read_text(encoding="utf-8"), re.MULTILINE | re.IGNORECASE)
    assert match, "client_max_body_size is not set"
    limit = int(match.group(1)) * UNITS[match.group(2).lower()]
    assert KB_MAX_UPLOAD_BYTES <= limit <= 2 * KB_MAX_UPLOAD_BYTES
