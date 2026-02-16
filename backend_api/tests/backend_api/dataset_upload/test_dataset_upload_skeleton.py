"""
Data asset upload (formerly dataset upload) API tests.

Covers the highest-priority "data asset creation with standardized metadata"
scenarios from TEST_REQUIREMENTS_MAP:

- FR-DAT-001: Data asset creation with standardized metadata
- FR-META-001: Metadata validation constraints + forbid extra fields

These tests hit the real FastAPI endpoint:
POST /api/v1/data-assets

Notes:
- Auth is required (get_current_user dependency). We use deterministic test tokens
  supported by AuthService.decode_token (e.g. "token-for-role:publisher").
- Data asset creation requires a real draft_id; we create one via POST /api/v1/drafts.
"""
from __future__ import annotations

import pytest


def _auth_header(role: str = "publisher") -> dict[str, str]:
    """Return an Authorization header using deterministic test tokens."""
    return {"Authorization": f"Bearer token-for-role:{role}"}


def _audit_context(client_request_id: str) -> dict:
    """Generate a minimal audit_context payload accepted by schemas.AuditContext."""
    return {
        "actor_user_id": "u-submit-1",
        "actor_role": "publisher",
        "timestamp_utc": "2026-01-30T12:45:00Z",
        "client_request_id": client_request_id,
    }


async def _create_draft(async_client) -> str:
    """
    Create a draft via the real API and return draft_id.

    Draft schema is the full "package" model (DataProductPackage).
    """
    draft_payload = {
        "package": {
            "product": {
                "name": "pkg-metadata-tests",
                "domain": "pharma",
                "owner_group": "default",
                "steward_user_id": "u-stew-1",
                "version_intent": "minor",
            },
            "dataset": {
                "format": "csv",
                "storage_ref": "s3://bucket/path/file.csv",
                "hash_sha256": "a" * 64,
                "row_count": 0,
                "contains_phi": False,
            },
            "schema": None,
            "controls": {"classification": "internal", "retention": None},
            "sop_references": [],
        },
        "audit_context": _audit_context("req-create-draft-1"),
    }

    resp = await async_client.post(
        "/api/v1/drafts",
        json=draft_payload,
        headers=_auth_header("publisher"),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "draft_id" in body
    return body["draft_id"]


@pytest.mark.api
@pytest.mark.anyio
async def test_data_asset_creation_with_valid_metadata(async_client):
    """
    FR-DAT-001, FR-META-001

    Acceptance criteria:
    - Title: 1-200 chars
    - Owner: 1-120 chars
    - Description optional
    - Returns: data_asset_id, metadata fields, state='validating'
    """
    draft_id = await _create_draft(async_client)

    payload = {
        "draft_id": draft_id,
        "metadata": {
            "title": "My Data Asset",
            "description": "Optional description",
            "owner": "user@example.com",
        },
        "audit_context": _audit_context("req-create-da-1"),
    }

    resp = await async_client.post(
        "/api/v1/data-assets",
        json=payload,
        headers=_auth_header("publisher"),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["data_asset_id"].startswith("sub-")
    assert body["title"] == "My Data Asset"
    assert body["description"] == "Optional description"
    assert body["owner"] == "user@example.com"
    assert body["state"] == "validating"
    assert "created_at_utc" in body
    assert "audit_event_id" in body


@pytest.mark.api
@pytest.mark.anyio
async def test_data_asset_creation_rejects_extra_fields(async_client):
    """
    FR-META-001

    Acceptance criteria:
    - metadata contains extra field -> 422
    - Pydantic models use extra='forbid'
    """
    draft_id = await _create_draft(async_client)

    payload = {
        "draft_id": draft_id,
        "metadata": {
            "title": "My Data Asset",
            "description": "Optional description",
            "owner": "user@example.com",
            "tags": ["should", "fail"],  # extra field forbidden
        },
        "audit_context": _audit_context("req-extra-fields-1"),
    }

    resp = await async_client.post(
        "/api/v1/data-assets",
        json=payload,
        headers=_auth_header("publisher"),
    )
    assert resp.status_code == 422
    # FastAPI/Pydantic v2 error format may vary; assert it's a validation error.
    body = resp.json()
    assert "detail" in body


@pytest.mark.api
@pytest.mark.anyio
@pytest.mark.parametrize(
    "title,expected_status",
    [
        ("", 422),  # min_length=1
        (" " * 5, 422),  # whitespace-only rejected by validator
        ("a", 201),
        ("a" * 200, 201),
        ("a" * 201, 422),  # max_length=200
    ],
)
async def test_data_asset_creation_title_length_constraints(async_client, title: str, expected_status: int):
    """
    FR-META-001

    Title constraints:
    - Empty -> 422
    - Whitespace-only -> 422
    - 1 char -> success
    - 200 chars -> success
    - >200 -> 422
    """
    draft_id = await _create_draft(async_client)

    payload = {
        "draft_id": draft_id,
        "metadata": {
            "title": title,
            "description": None,
            "owner": "user@example.com",
        },
        "audit_context": _audit_context(f"req-title-{expected_status}-{len(title)}"),
    }

    resp = await async_client.post(
        "/api/v1/data-assets",
        json=payload,
        headers=_auth_header("publisher"),
    )

    assert resp.status_code == expected_status, resp.text


@pytest.mark.api
@pytest.mark.anyio
@pytest.mark.parametrize(
    "owner,expected_status",
    [
        (None, 422),  # missing required field
        ("", 422),  # min_length=1
        (" " * 3, 422),  # whitespace-only rejected
        ("u", 201),
        ("u" * 120, 201),
        ("u" * 121, 422),
    ],
)
async def test_data_asset_creation_owner_required(async_client, owner, expected_status: int):
    """
    FR-META-001

    Owner constraints:
    - Missing/empty/whitespace-only -> 422
    - 1..120 -> success
    - >120 -> 422
    """
    draft_id = await _create_draft(async_client)

    metadata = {"title": "Owner Constraint Test", "description": None}
    if owner is not None:
        metadata["owner"] = owner

    payload = {
        "draft_id": draft_id,
        "metadata": metadata,
        "audit_context": _audit_context("req-owner-constraints-1"),
    }

    resp = await async_client.post(
        "/api/v1/data-assets",
        json=payload,
        headers=_auth_header("publisher"),
    )

    assert resp.status_code == expected_status, resp.text


@pytest.mark.api
@pytest.mark.anyio
@pytest.mark.parametrize(
    "description,expected_status,expected_description",
    [
        (None, 201, None),
        ("", 201, None),  # trimmed to None by validator
        ("   ", 201, None),  # trimmed to None
        ("x" * 2000, 201, "x" * 2000),
        ("x" * 2001, 422, None),
    ],
)
async def test_data_asset_creation_description_optional(async_client, description: str | None, expected_status: int, expected_description):
    """
    FR-META-001

    Description behavior:
    - None -> success
    - empty/whitespace -> success (treated as null)
    - <=2000 -> success
    - >2000 -> 422
    """
    draft_id = await _create_draft(async_client)

    payload = {
        "draft_id": draft_id,
        "metadata": {
            "title": "Description Optional Test",
            "description": description,
            "owner": "user@example.com",
        },
        "audit_context": _audit_context("req-desc-optional-1"),
    }

    resp = await async_client.post(
        "/api/v1/data-assets",
        json=payload,
        headers=_auth_header("publisher"),
    )

    assert resp.status_code == expected_status, resp.text

    if expected_status == 201:
        body = resp.json()
        assert body.get("description") == expected_description
