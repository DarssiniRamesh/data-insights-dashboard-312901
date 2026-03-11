import os
import sys
import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure backend_api/src is importable in test runs.
#
# Rationale:
# - pytest.ini contains `pythonpath = src`, but that setting requires
#   pytest's python_path support to be active; in some environments it is not.
# - We keep this fix test-only (per instructions not to modify app code).
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _BACKEND_ROOT / "src"
if _SRC_DIR.exists():
    sys.path.insert(0, str(_SRC_DIR))


@pytest.fixture(scope="session", autouse=True)
def _isolated_sqlite_db_for_tests() -> Iterator[str]:
    """
    Ensure tests never use the persisted repository DB.

    Why:
      - The repo contains backend_api/data/app.db which may already include rows.
      - Some API contract tests create a submission using a deterministic
        name/version; if the persisted DB is used, this can return 409 conflicts.
      - Test runs must be isolated and repeatable (GxP dev compliance expectation).

    Implementation:
      - Create a temporary SQLite file and point SQLITE_DB_PATH at it for the
        duration of the pytest session.
      - If the database module was imported earlier, close its global connection
        so subsequent calls will use the new path.
    """
    fd, path = tempfile.mkstemp(prefix="backend_api_test_", suffix=".sqlite3")
    os.close(fd)

    old_path = os.environ.get("SQLITE_DB_PATH")
    os.environ["SQLITE_DB_PATH"] = path

    # Best-effort: reset any already-open singleton connection.
    try:
        import database  # type: ignore

        if hasattr(database, "close_connection"):
            database.close_connection()
    except Exception:
        # Non-fatal: if not importable yet, it will pick up SQLITE_DB_PATH later.
        pass

    try:
        yield path
    finally:
        if old_path is None:
            os.environ.pop("SQLITE_DB_PATH", None)
        else:
            os.environ["SQLITE_DB_PATH"] = old_path

        try:
            os.remove(path)
        except FileNotFoundError:
            pass


@pytest.fixture(scope="session")
def app():
    """
    Provides the FastAPI app instance.

    Note:
      - Lifespan startup must run for schema init + required seed users
        (including deterministic 'system' user for audit FK safety).
    """
    from api.main import app as fastapi_app

    return fastapi_app


@pytest.fixture()
async def async_client(app) -> AsyncIterator[AsyncClient]:
    """
    HTTPX AsyncClient bound to the ASGI app, enabling API tests without
    running an external uvicorn server.

    Why we manually manage lifespan:
      - httpx's ASGITransport does not reliably run FastAPI lifespan hooks in all
        versions/configurations.
      - This project initializes the SQLite schema + seeds required users in the
        FastAPI *lifespan* (not in router startup events).
      - Many API routes expect tables like `users`/`submissions` to exist.

    Therefore:
      - Enter the app's lifespan context explicitly for each test using async_client.
      - This guarantees init_db()/seed_test_users() ran against our isolated SQLite DB.
    """
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


@pytest.fixture()
def temp_sqlite_path() -> Iterator[str]:
    """
    Temporary SQLite DB file path (kept for compatibility with existing tests).

    Some tests accept this fixture but don't use it directly; it remains useful
    for future integration tests that need their own DB file.
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
