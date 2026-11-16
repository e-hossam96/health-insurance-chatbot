from __future__ import annotations

from fastapi import HTTPException


def api_error(code: str, message: str, status: int, headers: dict[str, str] | None = None) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"error": {"code": code, "message": message}},
        headers=headers,
    )


def not_found(message: str) -> HTTPException:
    return api_error("not_found", message, 404)


def not_authenticated() -> HTTPException:
    return api_error("not_authenticated", "Not authenticated.", 401)


def forbidden(message: str) -> HTTPException:
    return api_error("forbidden", message, 403)


def rate_limited(message: str, retry_after: int | None = None) -> HTTPException:
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    return api_error("rate_limited", message, 429, headers)
