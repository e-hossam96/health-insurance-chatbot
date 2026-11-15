import prometheus_client
import pytest
from httpx import ASGITransport, AsyncClient

from backend.app import app


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    collectors = list(prometheus_client.REGISTRY._names_to_collectors.values())
    for c in collectors:
        if hasattr(c, "_metrics"):
            c._metrics.clear()


@pytest.mark.anyio()
async def test_metrics_uses_route_template() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/items/42")
        assert response.status_code == 200

        metrics_response = await client.get("/metrics")
        assert metrics_response.status_code == 200
        body = metrics_response.text

        assert 'route="/items/{item_id}"' in body
        assert 'route="/items/42"' not in body
