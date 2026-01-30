import pytest


@pytest.mark.api
@pytest.mark.anyio
async def test_health_check_root_returns_healthy(async_client):
    """
    FRD-BASE-HEALTH: Service exposes a basic health endpoint for readiness checks.
    NFR-OBS-HEALTH: Health endpoint must be fast and return a deterministic payload.
    """
    resp = await async_client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"message": "Healthy"}


@pytest.mark.api
@pytest.mark.anyio
async def test_health_check_root_disallows_post(async_client):
    """
    NFR-SEC-HTTP: Endpoint should not accept unsupported methods.
    """
    resp = await async_client.post("/")
    # FastAPI returns 405 for unsupported methods by default.
    assert resp.status_code == 405
