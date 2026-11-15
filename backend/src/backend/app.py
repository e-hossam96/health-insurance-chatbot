from fastapi import FastAPI

from backend.metrics import prometheus_middleware

app = FastAPI(title="Health Insurance Chatbot")
app.middleware("http")(prometheus_middleware)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/items/{item_id}")
async def get_item(item_id: int) -> dict[str, int]:
    return {"item_id": item_id}
