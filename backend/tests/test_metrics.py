from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app import app
from testkit.metrics import label_sets, metric_value

TEMPLATE = "/me/sessions/{chat_session_id}/messages"


@pytest.mark.anyio()
async def test_H3_H4_http_metrics_use_the_route_template_with_status_and_latency() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        before = (await client.get("/metrics")).text
        assert (await client.get("/me/sessions/42/messages")).status_code == 401
        after = (await client.get("/metrics")).text

    labels = {"method": "GET", "route": TEMPLATE, "status": "401"}
    assert metric_value(after, "http_requests_total", labels) == metric_value(before, "http_requests_total", labels) + 1
    duration = {"method": "GET", "route": TEMPLATE}
    assert metric_value(after, "http_request_duration_seconds_count", duration) == metric_value(before, "http_request_duration_seconds_count", duration) + 1
    assert 'route="/me/sessions/42/messages"' not in after


@pytest.mark.anyio()
async def test_H4_unknown_urls_share_one_fixed_route_label() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/nope/123", "/nope/456", "/random-9f3a"):
            assert (await client.get(path)).status_code == 404
        exposition = (await client.get("/metrics")).text
    routes = {dict(labels).get("route") for labels in label_sets(exposition, ("http_",))["http_requests"]}
    assert "unmatched" in routes
    assert not any(route and ("nope" in route or "random" in route) for route in routes)


@pytest.mark.anyio()
async def test_H3_fixed_label_counters_are_exposed_at_zero_before_the_first_event() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        exposition = (await client.get("/metrics")).text
    found = label_sets(exposition, ("card_actions", "chat_turns", "kb_ingest", "rate_limit_rejections", "chat_tokens"))
    card_actions = found["card_actions"]
    for action in ("book", "cancel", "complaint"):
        for outcome in ("ok", "conflict", "rejected", "error"):
            assert (("action", action), ("outcome", outcome)) in card_actions
    assert {(("outcome", outcome),) for outcome in ("ok", "error", "cancelled")} <= found["chat_turns"]
    assert {(("outcome", outcome),) for outcome in ("ok", "failed")} <= found["kb_ingest"]
    limits = ("chat_minute", "chat_daily", "message_length", "signup", "login")
    assert {(("limit", limit),) for limit in limits} <= found["rate_limit_rejections"]
    assert {(("kind", kind),) for kind in ("prompt", "completion")} <= found["chat_tokens"]
