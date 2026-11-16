from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}
# the KB upload streams the raw file so the size limit can be checked while reading (G2)
RAW_BODY_ROUTES = {("POST", "/admin/kb-documents")}


def _has_body(request: Request) -> bool:
    length = request.headers.get("content-length")
    return "transfer-encoding" in request.headers or (length is not None and length not in ("", "0"))


async def json_only_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    if (
        request.method in STATE_CHANGING
        and (request.method, request.url.path) not in RAW_BODY_ROUTES
        and _has_body(request)
        and "application/json" not in request.headers.get("content-type", "")
    ):
        return JSONResponse(
            status_code=422,
            content={"detail": {"error": {"code": "validation_error", "message": "Content-Type must be application/json."}}},
        )
    return await call_next(request)
