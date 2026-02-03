import pytest


def _todo(reason: str) -> str:
    # Small helper to keep xfail reasons consistent and searchable in CI.
    return f"TODO(workflow-not-implemented): {reason}"


@pytest.mark.integration
@pytest.mark.frd
@pytest.mark.xfail(reason=_todo("FRD-DPP-001 submission -> publish happy path endpoints/services missing"))
def test_e2e_happy_path_submission_to_publish(temp_sqlite_path, seed_submission_payload):
    """
    Feature: report_generation

    FRD-DPP-001: End-to-end flow: submission → pipeline processing → quality gates →
    validation → approval → publish.

    Intended assertions (once implemented):
    - Create submission returns 201 with submission_id/version
    - Pipeline processing transitions status to PROCESSED
    - Quality gates pass -> status QUALITY_PASSED
    - Validation complete -> status VALIDATED
    - Approval by approver (different user than submitter) -> status APPROVED
    - Publish -> status PUBLISHED with published URI/version lock
    """
    raise AssertionError("Implement workflow modules + endpoints, then enable this test.")


@pytest.mark.integration
@pytest.mark.frd
@pytest.mark.xfail(reason=_todo("FRD-DPP-002 invalid payload schema not implemented"))
def test_submission_rejects_invalid_payload():
    """
    Feature: dataset_upload / report_generation (input validation)

    FRD-DPP-002: Invalid payloads must be rejected with clear validation errors.

    Negative cases:
    - missing required fields (name/version/artifacts)
    - invalid semver format
    - empty artifacts list
    """
    raise AssertionError("Implement request schemas + validation.")


@pytest.mark.integration
@pytest.mark.frd
@pytest.mark.xfail(reason=_todo("FRD-DPP-003 duplicate submission/version conflict behavior not implemented"))
def test_duplicate_submission_version_conflict(seed_submission_payload):
    """
    Feature: dashboard_management (conflict handling surfaced in UI)

    FRD-DPP-003: Duplicate submissions and version conflicts are rejected.

    Intended setup:
    - Submit {name=X, version=1.0.0} -> success
    - Submit again same name+version -> 409 conflict (or domain-specific error)
    """
    raise AssertionError("Implement repository uniqueness + API error mapping.")


@pytest.mark.integration
@pytest.mark.frd
@pytest.mark.xfail(reason=_todo("FRD-DPP-004 quality gates failure handling not implemented"))
def test_quality_gate_failure_blocks_approval_and_publish():
    """
    Feature: report_generation

    FRD-DPP-004: Failed quality gates prevent approval/publish and produce evidence.

    Intended assertions:
    - Quality gate evaluation returns failure details (which gate, why)
    - Submission status remains QUALITY_FAILED
    - Approval/publish endpoints return 400/409 until gates are re-run and pass
    """
    raise AssertionError("Implement quality gate service + status machine + evidence store.")


@pytest.mark.integration
@pytest.mark.frd
@pytest.mark.xfail(reason=_todo("FRD-DPP-005 missing signatures/evidence enforcement not implemented"))
def test_missing_signatures_or_evidence_blocks_approval():
    """
    Feature: report_generation / dashboard_management

    FRD-DPP-005: Missing required signatures/evidence blocks approval.

    Intended assertions:
    - Attempt approval without required evidence -> 400/422
    - Evidence list endpoint shows missing evidence requirements
    """
    raise AssertionError("Implement evidence utilities + approval preconditions.")


@pytest.mark.integration
@pytest.mark.frd
@pytest.mark.xfail(reason=_todo("FRD-DPP-006 segregation-of-duties enforcement not implemented"))
def test_sod_violation_submitter_cannot_approve(auth_context_submitter):
    """
    Feature: dashboard_management (governance controls)

    FRD-DPP-006: Segregation-of-duties (SoD): submitter cannot approve own submission.

    Intended assertions:
    - Submitter creates submission
    - Same user attempts approval -> 403 SoD violation
    """
    raise AssertionError("Implement auth context, RBAC, SoD checks.")


@pytest.mark.integration
@pytest.mark.frd
@pytest.mark.xfail(reason=_todo("FRD-DPP-007 publish error handling not implemented"))
def test_publish_error_results_in_retryable_state():
    """
    Feature: report_generation / dashboard_management

    FRD-DPP-007: Publish errors should be captured and state set appropriately.

    Intended assertions:
    - Publish attempt fails due to downstream error (e.g., storage write)
    - Status becomes PUBLISH_FAILED with error details
    - Subsequent retry is possible if error is transient
    """
    raise AssertionError("Implement publisher adapter + error mapping + retry policy.")
