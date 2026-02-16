"""
Report generation / validation report retrieval tests.

The repo's "report_generation" feature is currently represented by the validation
pipeline and its tamper-evident validation report artifact.

This module upgrades the previous skeleton/skip with real tests covering:

- FR-VAL-001: Validation pipeline execution produces checks + overall_status
- FR-EVD-001 (partial): Validation report includes a SHA-256 hash field
- API contract: GET /api/v1/validation-runs/{validation_run_id}

Flow:
1) Create draft
2) Create data asset from draft (standardized metadata)
3) Trigger validation run for that asset
4) Retrieve validation report by validation_run_id
"""
from __future__ import annotations

import pytest


def _auth_header(role: str = "publisher") -> dict[str, str]:
    return {"Authorization": f"Bearer token-for-role:{role}"}


def _audit_context(client_request_id: str) -> dict:
    return {
        "actor_user_id": "u-submit-1",
        "actor_role": "publisher",
        "timestamp_utc": "2026-01-30T12:45:00Z",
        "client_request_id": client_request_id,
    }


async def _create_draft(async_client) -> str:
    draft_payload = {
        "package": {
            "product": {
                "name": "pkg-validation-tests",
                "domain": "pharma",
                "owner_group": "default",
                "steward_user_id": "u-stew-1",
                "version_intent": "minor",
            },
            "dataset": {
                "format": "csv",
                "storage_ref": "s3://bucket/path/file.csv",
                "hash_sha256": "b" * 64,
                "row_count": 0,
                "contains_phi": False,
            },
            "schema": None,
            "controls": {"classification": "internal", "retention": None},
            "sop_references": [],
        },
        "audit_context": _audit_context("req-create-draft-val-1"),
    }

    resp = await async_client.post(
        "/api/v1/drafts",
        json=draft_payload,
        headers=_auth_header("publisher"),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["draft_id"]


async def _create_data_asset(async_client) -> str:
    draft_id = await _create_draft(async_client)
    payload = {
        "draft_id": draft_id,
        "metadata": {"title": "Validation Test Asset", "description": None, "owner": "user@example.com"},
        "audit_context": _audit_context("req-create-da-val-1"),
    }
    resp = await async_client.post("/api/v1/data-assets", json=payload, headers=_auth_header("publisher"))
    assert resp.status_code == 201, resp.text
    return resp.json()["data_asset_id"]


@pytest.mark.api
@pytest.mark.anyio
async def test_validation_trigger_and_retrieve_report(async_client):
    """
    FR-VAL-001, FR-EVD-001 (report hash field)

    Assertions:
    - trigger returns pipeline_job_id (=validation_run_id) and state='completed'
    - GET validation report returns stable schema:
        validation_run_id, overall_status, checks(list), report_hash_sha256, created_at_utc
    - report_hash_sha256 looks like sha256 hex (len=64)
    """
    data_asset_id = await _create_data_asset(async_client)

    trigger_payload = {"validation_profile": "baseline", "audit_context": _audit_context("req-trigger-val-1")}
    trigger = await async_client.post(
        f"/api/v1/data-assets/{data_asset_id}/validate",
        json=trigger_payload,
        headers=_auth_header("publisher"),
    )
    assert trigger.status_code == 200, trigger.text
    trigger_body = trigger.json()
    validation_run_id = trigger_body["pipeline_job_id"]
    assert trigger_body["state"] == "completed"
    assert trigger_body["audit_event_id"] == validation_run_id

    get_report = await async_client.get(
        f"/api/v1/validation-runs/{validation_run_id}",
        headers=_auth_header("publisher"),
    )
    assert get_report.status_code == 200, get_report.text
    report = get_report.json()

    assert report["validation_run_id"] == validation_run_id
    assert report["overall_status"] in {"pass", "fail"}
    assert isinstance(report["checks"], list)
    assert isinstance(report["report_hash_sha256"], str)
    assert len(report["report_hash_sha256"]) == 64
    assert isinstance(report["created_at_utc"], str)


@pytest.mark.api
@pytest.mark.anyio
async def test_validation_report_missing_id_returns_404(async_client):
    """
    API contract negative: unknown validation_run_id should return 404.
    """
    resp = await async_client.get(
        "/api/v1/validation-runs/val-does-not-exist",
        headers=_auth_header("publisher"),
    )
    assert resp.status_code == 404
    body = resp.json()
    assert "detail" in body
