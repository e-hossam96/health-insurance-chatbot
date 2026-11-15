import time
from collections.abc import Awaitable, Callable

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "route", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "route"],
)


def _get_route_template(request: Request) -> str:
    app = request.app
    for route in app.routes:
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            return getattr(route, "path", request.url.path)
    return request.url.path


async def prometheus_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if request.url.path == "/metrics":
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    route = _get_route_template(request)
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start

    http_requests_total.labels(
        method=request.method,
        route=route,
        status=response.status_code,
    ).inc()
    http_request_duration_seconds.labels(
        method=request.method,
        route=route,
    ).observe(elapsed)

    return response
