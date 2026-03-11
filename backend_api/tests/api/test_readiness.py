import pytest


@pytest.mark.api
@pytest.mark.anyio
async def test_readiness_returns_200_when_db_initialized(async_client):
    """
    Readiness contract:
    - /ready should return 200 only when DB is reachable and schema init completed.
    - In tests, we run the FastAPI lifespan context in the async_client fixture, so
      the DB must be initialized and ready.
    """
    resp = await async_client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["db"]["ok"] is True
    assert body["db"]["initialized"] is True
    assert "path" in body["db"]
    assert "degraded" in body["db"]
