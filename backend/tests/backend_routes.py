from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.routing import BaseRoute

HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def _walk(routes: list[BaseRoute], prefix: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for route in routes:
        if isinstance(route, APIRoute):
            found += [
                (method, prefix + route.path)
                for method in route.methods
                if method in HTTP_METHODS
            ]
        elif hasattr(route, "original_router"):
            # FastAPI wraps each included router; walking it also finds routes hidden from the OpenAPI schema
            found += _walk(
                route.original_router.routes, prefix + route.include_context.prefix
            )
    return found


def all_routes(app: FastAPI) -> set[tuple[str, str]]:
    return set(_walk(app.routes, ""))
