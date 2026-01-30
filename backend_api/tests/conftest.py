import os
import tempfile
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session")
def app():
    """
    Provides the FastAPI app instance.

    Note: current codebase only exposes `src.api.main:app`.
    """
    from src.api.main import app as fastapi_app

    return fastapi_app


@pytest.fixture()
async def async_client(app) -> AsyncIterator[AsyncClient]:
    """
    HTTPX AsyncClient bound to the ASGI app, enabling API tests without
    running an external uvicorn server.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture()
def temp_sqlite_path() -> Iterator[str]:
    """
    Temporary SQLite DB file path for integration tests.

    The current backend implementation does not yet use SQLite; this fixture is
    provided for future repository/service tests and integration tests.
    """
    fd, path = tempfile.mkstemp(prefix="test_", suffix=".sqlite3")
    os.close(fd)
    try:
        yield path
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


@pytest.fixture()
def auth_context_submitter() -> dict:
    """
    Placeholder auth context for a 'submitter' role.

    Current backend has no auth; future tests will use this to simulate RBAC and
    segregation-of-duties (SoD).
    """
    return {"user_id": "u_submitter", "roles": ["submitter"]}


@pytest.fixture()
def auth_context_approver() -> dict:
    """
    Placeholder auth context for an 'approver' role.

    Current backend has no auth; future tests will use this to simulate RBAC and
    segregation-of-duties (SoD).
    """
    return {"user_id": "u_approver", "roles": ["approver"]}


@pytest.fixture()
def seed_submission_payload() -> dict:
    """
    Seed payload for data product submission.

    Matches the intended submission -> pipeline -> quality gates -> validation ->
    approval -> publish flow; will be aligned to the real Pydantic schema once implemented.
    """
    return {
        "name": "example-data-product",
        "version": "1.0.0",
        "description": "Example data product used for tests.",
        "artifacts": [{"type": "dataset", "uri": "s3://bucket/path/file.csv"}],
        "metadata": {"domain": "pharma", "gxp": True},
    }
