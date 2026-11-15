from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import uvicorn
from starlette.types import ASGIApp

START_TIMEOUT_S = 15.0


class _ReadyServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config) -> None:
        super().__init__(config)
        self.ready = threading.Event()

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets)
        self.ready.set()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


@contextmanager
def serve_in_thread(app: ASGIApp) -> Iterator[str]:
    port = free_port()
    server = _ReadyServer(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", loop="asyncio", lifespan="on")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    if not server.ready.wait(START_TIMEOUT_S):
        server.should_exit = True
        raise RuntimeError("live server did not start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(START_TIMEOUT_S)
