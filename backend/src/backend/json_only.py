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


def _is_cross_site_capable(request: Request) -> bool:
    content_type = request.headers.get("content-type")
    if content_type is not None:
        # an HTML form can send these types with an empty body and no CORS preflight (B10)
        return "application/json" not in content_type
    return _has_body(request)


async def json_only_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    if (
        request.method in STATE_CHANGING
        and (request.method, request.url.path) not in RAW_BODY_ROUTES
        and _is_cross_site_capable(request)
    ):
        return JSONResponse(
            status_code=422,
            content={"detail": {"error": {"code": "validation_error", "message": "Content-Type must be application/json."}}},
        )
    return await call_next(request)
