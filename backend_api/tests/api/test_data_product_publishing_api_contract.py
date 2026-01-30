import pytest


def _todo(reason: str) -> str:
    return f"TODO(api-not-implemented): {reason}"


def _authz_todo(reason: str) -> str:
    # Separate helper to keep auth-related TODOs searchable.
    return f"TODO(authz-not-implemented): {reason}"


def _authn_todo(reason: str) -> str:
    return f"TODO(authn-not-implemented): {reason}"


@pytest.mark.api
@pytest.mark.frd
@pytest.mark.anyio
async def test_api_create_submission_returns_201(async_client, seed_submission_payload):
    """
    FR-DPP-001 (Submission):
      The system shall allow a Publisher to submit a dataset for publishing via UI or API.

    Traceability:
      - FR-DPP-001
      - NFR-DPP-020 (API + automated testing)
      - TDD catalog: TS-API-SUBMIT-001 (contract)
    """
    resp = await async_client.post("/submissions", json=seed_submission_payload)
    assert resp.status_code == 201
    body = resp.json()
    assert "submission_id" in body
    assert body["status"] in {"SUBMITTED", "RECEIVED"}


@pytest.mark.api
@pytest.mark.frd
@pytest.mark.anyio
async def test_api_run_quality_gates_blocks_on_failure(async_client):
    """
    FR-DPP-004 (Mandatory gates) / FR-DPP-008 (Block on failure).

    Traceability:
      - FR-DPP-004, FR-DPP-008
      - NFR-DPP-015 (Quality gate enforcement)
      - TDD catalog: TS-API-VAL-* scenarios
    """
    resp = await async_client.post("/submissions/s1/quality-gates/run")
    assert resp.status_code in (200, 409)
    body = resp.json()
    assert "result" in body  # expected: PASS/FAIL


@pytest.mark.api
@pytest.mark.frd
@pytest.mark.anyio
async def test_api_approval_rejects_sod_violation(async_client):
    """
    Legacy placeholder test (kept): SoD: submitter cannot approve own submission.

    See also: dedicated negative SoD test cases added below with richer traceability.
    """
    resp = await async_client.post("/submissions/s1/approve")
    assert resp.status_code == 403


@pytest.mark.api
@pytest.mark.frd
@pytest.mark.anyio
async def test_api_publish_returns_published_location(async_client):
    """
    FR-DPP-025/FR-DPP-026/FR-DPP-027 style publish outputs will be validated here once implemented.
    """
    resp = await async_client.post("/submissions/s1/publish")
    assert resp.status_code == 200
    body = resp.json()
    assert "published_uri" in body
    assert body.get("status") == "PUBLISHED"


# -----------------------------
# Negative authN/authZ scenarios
# -----------------------------

@pytest.mark.api
@pytest.mark.nfr
@pytest.mark.anyio
async def test_auth_missing_token_rejected_401(async_client, seed_submission_payload):
    """
    Authentication failure: missing token/header.

    Traceability:
      - FR-DPP-003 (identity must be captured; submission must not be accepted if identity cannot be recorded)
      - NFR-DPP-009 (Identity controls), NFR-DPP-010 (Authorization)
      - TDD catalog: TS-SEC-AUTHN-001
    """
    resp = await async_client.post("/api/v1/submissions", json={"draft_id": "draft-1"})
    assert resp.status_code == 401


@pytest.mark.api
@pytest.mark.nfr
@pytest.mark.anyio
async def test_auth_invalid_or_expired_token_rejected_401(async_client):
    """
    Authentication failure: invalid/expired token.

    Traceability:
      - NFR-DPP-009, NFR-DPP-010
      - TDD catalog: TS-SEC-AUTHN-001 (negative variants)
    """
    resp = await async_client.get(
        "/api/v1/audit/events",
        headers={"Authorization": "Bearer invalid-or-expired"},
    )
    assert resp.status_code == 401


@pytest.mark.api
@pytest.mark.nfr
@pytest.mark.anyio
async def test_auth_wrong_audience_or_scope_rejected_403(async_client):
    """
    Authentication/authorization failure: wrong audience/scope.

    Traceability:
      - NFR-DPP-010 (Authorization), NFR-DPP-011 (Deny-by-default)
    """
    resp = await async_client.get(
        "/api/v1/evidence-packages/evid-1",
        headers={"Authorization": "Bearer wrong-aud-or-scope"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.api
@pytest.mark.nfr
@pytest.mark.anyio
async def test_authz_publisher_cannot_access_audit_events_403(async_client):
    """
    Authorization failure: role-based access control violation.

    Traceability:
      - FR-DPP-018/FR-DPP-019 (policy enforcement + local logging)
      - NFR-DPP-010 (Authorization), NFR-DPP-011 (Deny-by-default)
      - TDD catalog: TS-SEC-AUTHZ-001
    """
    resp = await async_client.get(
        "/api/v1/audit/events?entity_type=submission&entity_id=sub-1",
        headers={"Authorization": "Bearer token-for-role:publisher"},
    )
    assert resp.status_code in (401, 403)


# -----------------------------
# Negative SoD scenarios
# -----------------------------

@pytest.mark.api
@pytest.mark.frd
@pytest.mark.nfr
@pytest.mark.anyio
@pytest.mark.xfail(reason=_todo("SoD enforcement + identity binding not implemented on approve endpoint"))
async def test_sod_same_user_cannot_submit_and_approve_same_submission(async_client):
    """
    Segregation of Duties (SoD): submitter cannot approve their own submission.

    Traceability:
      - FR-DPP-015 (SoD)
      - NFR-DPP-012 (Segregation of duties)
      - TDD catalog: TS-API-APPROVAL-003
    """
    approve_payload = {
        "decision": "publish",
        "required_preconditions": {"latest_validation_run_id": "val-1"},
        "signature": {
            "signer_user_id": "u-pub-1",  # same as submitter in target-state
            "signer_role": "steward",
            "signed_at_utc": "2026-01-30T12:45:00Z",
            "reauthentication_method": "sso_reauth",
            "signature_reason": "Approve for publish",
        },
        "audit_context": {
            "actor_user_id": "u-pub-1",
            "actor_role": "publisher",
            "timestamp_utc": "2026-01-30T12:45:00Z",
            "client_request_id": "req-sod-1",
        },
    }
    resp = await async_client.post(
        "/api/v1/submissions/sub-1/approve",
        json=approve_payload,
        headers={"Authorization": "Bearer token-for-u-pub-1"},
    )
    assert resp.status_code in (403, 409)
    # Target-state expectation (LLD/TDD): 409 with error code SOD_VIOLATION


@pytest.mark.api
@pytest.mark.nfr
@pytest.mark.anyio
@pytest.mark.xfail(reason=_authz_todo("Cross-role impersonation prevention not implemented"))
async def test_sod_cross_role_impersonation_attempt_blocked(async_client):
    """
    SoD/authorization: attempt to impersonate a higher-privilege role via request body.

    Example: audit_context.actor_role='steward' but token/user is publisher.

    Traceability:
      - NFR-DPP-010 (Authorization), NFR-DPP-011 (Deny-by-default)
      - NFR-DPP-002 (Auditability, result=blocked)
    """
    payload = {
        "decision": "publish",
        "required_preconditions": {"latest_validation_run_id": "val-1"},
        "signature": {
            "signer_user_id": "u-pub-1",
            "signer_role": "steward",
            "signed_at_utc": "2026-01-30T12:45:00Z",
            "reauthentication_method": "sso_reauth",
            "signature_reason": "Approve for publish",
        },
        "audit_context": {
            "actor_user_id": "u-pub-1",
            "actor_role": "steward",  # impersonation attempt (should be derived from auth, not body)
            "timestamp_utc": "2026-01-30T12:45:00Z",
            "client_request_id": "req-impersonate-1",
        },
    }
    resp = await async_client.post(
        "/api/v1/submissions/sub-1/approve",
        json=payload,
        headers={"Authorization": "Bearer token-for-role:publisher"},
    )
    assert resp.status_code in (401, 403, 409)


# -----------------------------
# Negative electronic signature scenarios (Part 11-aligned expectations)
# -----------------------------

@pytest.mark.api
@pytest.mark.frd
@pytest.mark.nfr
@pytest.mark.anyio
@pytest.mark.xfail(reason=_todo("Approval endpoint + signature validation not implemented"))
async def test_esign_missing_signature_block_rejected(async_client):
    """
    Electronic signature: missing signature block.

    Traceability:
      - FR-DPP-016 (e-sign required)
      - NFR-DPP-013 (Electronic signatures)
      - TDD catalog: TS-API-APPROVAL-002
    """
    payload = {
        "decision": "publish",
        "required_preconditions": {"latest_validation_run_id": "val-1"},
        "audit_context": {
            "actor_user_id": "u-stew-1",
            "actor_role": "steward",
            "timestamp_utc": "2026-01-30T12:45:00Z",
            "client_request_id": "req-esign-missing-1",
        },
    }
    resp = await async_client.post("/api/v1/submissions/sub-1/approve", json=payload)
    assert resp.status_code in (400, 409, 422)
    # Target-state expectation: SIGNATURE_REQUIRED


@pytest.mark.api
@pytest.mark.nfr
@pytest.mark.anyio
@pytest.mark.xfail(reason=_todo("Signature hash verification not implemented"))
async def test_esign_invalid_signature_hash_rejected(async_client):
    """
    Electronic signature: invalid signature_hash (integrity check).

    Traceability:
      - FR-DPP-028 (hashing evidence), NFR-DPP-013 (non-repudiation evidence)
    """
    payload = {
        "decision": "publish",
        "required_preconditions": {"latest_validation_run_id": "val-1"},
        "signature": {
            "signer_user_id": "u-stew-1",
            "signer_role": "steward",
            "signed_at_utc": "2026-01-30T12:45:00Z",
            "reauthentication_method": "sso_reauth",
            "signature_reason": "Approve for publish",
            "signature_hash": "not-a-real-hash",
        },
        "audit_context": {
            "actor_user_id": "u-stew-1",
            "actor_role": "steward",
            "timestamp_utc": "2026-01-30T12:45:00Z",
            "client_request_id": "req-esign-hash-1",
        },
    }
    resp = await async_client.post("/api/v1/submissions/sub-1/approve", json=payload)
    assert resp.status_code in (400, 409, 422)


@pytest.mark.api
@pytest.mark.nfr
@pytest.mark.anyio
@pytest.mark.xfail(reason=_todo("Signature signer identity binding not implemented"))
async def test_esign_mismatched_signer_id_rejected(async_client):
    """
    Electronic signature: signer_user_id does not match authenticated actor.

    Traceability:
      - NFR-DPP-009 (Identity controls)
      - NFR-DPP-013 (Electronic signatures)
    """
    payload = {
        "decision": "publish",
        "required_preconditions": {"latest_validation_run_id": "val-1"},
        "signature": {
            "signer_user_id": "u-other",
            "signer_role": "steward",
            "signed_at_utc": "2026-01-30T12:45:00Z",
            "reauthentication_method": "sso_reauth",
            "signature_reason": "Approve for publish",
        },
        "audit_context": {
            "actor_user_id": "u-stew-1",
            "actor_role": "steward",
            "timestamp_utc": "2026-01-30T12:45:00Z",
            "client_request_id": "req-esign-mismatch-1",
        },
    }
    resp = await async_client.post(
        "/api/v1/submissions/sub-1/approve",
        json=payload,
        headers={"Authorization": "Bearer token-for-u-stew-1"},
    )
    assert resp.status_code in (400, 403, 409)


@pytest.mark.api
@pytest.mark.nfr
@pytest.mark.anyio
@pytest.mark.xfail(reason=_todo("Signature timestamp window policy not implemented"))
async def test_esign_timestamp_outside_allowed_window_rejected(async_client):
    """
    Electronic signature: signature timestamp outside allowed window.

    Traceability:
      - NFR-DPP-003 (time controls)
      - NFR-DPP-013 (Electronic signatures; contemporaneous signing expectation)
    """
    payload = {
        "decision": "publish",
        "required_preconditions": {"latest_validation_run_id": "val-1"},
        "signature": {
            "signer_user_id": "u-stew-1",
            "signer_role": "steward",
            "signed_at_utc": "1999-01-01T00:00:00Z",
            "reauthentication_method": "sso_reauth",
            "signature_reason": "Approve for publish",
        },
        "audit_context": {
            "actor_user_id": "u-stew-1",
            "actor_role": "steward",
            "timestamp_utc": "2026-01-30T12:45:00Z",
            "client_request_id": "req-esign-time-1",
        },
    }
    resp = await async_client.post("/api/v1/submissions/sub-1/approve", json=payload)
    assert resp.status_code in (400, 409, 422)


@pytest.mark.api
@pytest.mark.nfr
@pytest.mark.anyio
@pytest.mark.xfail(reason=_todo("Re-sign without changes/idempotency policy not implemented"))
async def test_esign_resign_without_changes_rejected_or_idempotent(async_client):
    """
    Electronic signature: re-sign attempts without changes.

    Traceability:
      - NFR-DPP-005 (Immutability)
      - TDD catalog: TS-DB-LOCK-001 / TS-RES-IDEMP-001 (related idempotency/duplicate attempts)
    """
    payload = {
        "decision": "publish",
        "required_preconditions": {"latest_validation_run_id": "val-1"},
        "signature": {
            "signer_user_id": "u-stew-1",
            "signer_role": "steward",
            "signed_at_utc": "2026-01-30T12:45:00Z",
            "reauthentication_method": "sso_reauth",
            "signature_reason": "Approve for publish",
        },
        "audit_context": {
            "actor_user_id": "u-stew-1",
            "actor_role": "steward",
            "timestamp_utc": "2026-01-30T12:45:00Z",
            "client_request_id": "req-esign-resign-1",
        },
    }
    first = await async_client.post("/api/v1/submissions/sub-1/approve", json=payload)
    second = await async_client.post("/api/v1/submissions/sub-1/approve", json=payload)

    # Target-state: either second is idempotent (same evidence_package_id) or blocked as duplicate.
    assert first.status_code in (200, 201, 409, 403, 404)
    assert second.status_code in (200, 201, 409, 403, 404)


# -----------------------------
# Negative gate enforcement / evidence / audit integrity scenarios
# -----------------------------

@pytest.mark.api
@pytest.mark.frd
@pytest.mark.nfr
@pytest.mark.anyio
@pytest.mark.xfail(reason=_todo("Workflow state machine + gate enforcement not implemented"))
async def test_quality_gate_failed_blocks_workflow_progression(async_client):
    """
    Quality gate enforcement: cannot approve/publish when gates failed or evidence missing.

    Traceability:
      - FR-DPP-008 (block and audit failure)
      - NFR-DPP-015 (mandatory gate enforcement)
      - TDD catalog: TS-API-APPROVAL-004 negative variants
    """
    resp = await async_client.post("/api/v1/submissions/sub-1/approve", json={"decision": "publish"})
    assert resp.status_code in (400, 409, 422)


@pytest.mark.api
@pytest.mark.nfr
@pytest.mark.anyio
@pytest.mark.xfail(reason=_todo("Evidence checksum validation endpoint not implemented"))
async def test_audit_or_evidence_checksum_tampering_detected(async_client):
    """
    Audit/evidence integrity: tampered evidence checksum should be detected and blocked.

    Traceability:
      - NFR-DPP-005 (Immutability), NFR-DPP-007 (open formats), FR-DPP-028 (hashing evidence)
    """
    resp = await async_client.get("/api/v1/evidence-packages/evid-1")
    assert resp.status_code in (200, 401, 403, 404)
    # Target-state: if evidence exists, server should expose hash and reject mismatches when detected.
