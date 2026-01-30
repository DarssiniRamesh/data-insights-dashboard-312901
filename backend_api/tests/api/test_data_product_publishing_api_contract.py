import pytest


def _todo(reason: str) -> str:
    return f"TODO(api-not-implemented): {reason}"


@pytest.mark.api
@pytest.mark.frd
@pytest.mark.asyncio
@pytest.mark.xfail(reason=_todo("FRD-DPP-001 /submissions endpoint not implemented"))
async def test_api_create_submission_returns_201(async_client, seed_submission_payload):
    """
    FRD-DPP-001: Create submission endpoint exists and returns created resource info.
    """
    resp = await async_client.post("/submissions", json=seed_submission_payload)
    assert resp.status_code == 201
    body = resp.json()
    assert "submission_id" in body
    assert body["status"] in {"SUBMITTED", "RECEIVED"}


@pytest.mark.api
@pytest.mark.frd
@pytest.mark.asyncio
@pytest.mark.xfail(reason=_todo("FRD-DPP-004 quality gates endpoint not implemented"))
async def test_api_run_quality_gates_blocks_on_failure(async_client):
    """
    FRD-DPP-004: Quality gates endpoint returns pass/fail and evidence details.
    """
    resp = await async_client.post("/submissions/s1/quality-gates/run")
    assert resp.status_code in (200, 409)
    body = resp.json()
    assert "result" in body  # expected: PASS/FAIL


@pytest.mark.api
@pytest.mark.frd
@pytest.mark.asyncio
@pytest.mark.xfail(reason=_todo("FRD-DPP-006 approval endpoint and SoD checks not implemented"))
async def test_api_approval_rejects_sod_violation(async_client):
    """
    FRD-DPP-006: SoD: submitter cannot approve own submission.
    """
    # Intended: send auth header or token representing submitter.
    resp = await async_client.post("/submissions/s1/approve")
    assert resp.status_code == 403


@pytest.mark.api
@pytest.mark.frd
@pytest.mark.asyncio
@pytest.mark.xfail(reason=_todo("FRD-DPP-007 publish endpoint not implemented"))
async def test_api_publish_returns_published_location(async_client):
    """
    FRD-DPP-007: Publish endpoint returns published URI/location and immutable version.
    """
    resp = await async_client.post("/submissions/s1/publish")
    assert resp.status_code == 200
    body = resp.json()
    assert "published_uri" in body
    assert body.get("status") == "PUBLISHED"
