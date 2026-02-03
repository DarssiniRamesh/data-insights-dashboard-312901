import pytest


def _todo(reason: str) -> str:
    # Small helper to keep xfail reasons consistent and searchable in CI.
    return f"TODO(workflow-not-implemented): {reason}"


@pytest.mark.integration
@pytest.mark.frd
@pytest.mark.nfr
@pytest.mark.xfail(reason=_todo("AuthN/AuthZ seam + workflow endpoints not implemented"))
def test_integration_auth_missing_token_blocks_write_and_is_auditable():
    """
    Feature: dashboard_management (security + auditing)

    Integration negative: when auth is enabled, write endpoints must reject missing auth,
    and (policy-dependent) the denied attempt should be written to audit trail without
    leaking payload content.

    Traceability:
      - FR-DPP-003 (identity capture; do not accept if identity cannot be recorded)
      - NFR-DPP-009 (Identity controls)
      - NFR-DPP-010 / NFR-DPP-011 (Authorization / deny-by-default)
      - NFR-DPP-002 (Auditability)
      - TDD catalog: TS-SEC-AUTHN-001, TS-SEC-AUTHZ-001
    """
    raise AssertionError("Implement auth middleware + audit logging for denied access.")


@pytest.mark.integration
@pytest.mark.frd
@pytest.mark.nfr
@pytest.mark.xfail(reason=_todo("SoD enforcement not implemented in ApprovalService/DB"))
def test_integration_sod_violation_same_user_submit_and_approve_is_blocked_and_audited():
    """
    Feature: dashboard_management (governance controls + auditing)

    Integration negative: SoD violation should be blocked server-side and recorded
    as audit_events.result=blocked.

    Traceability:
      - FR-DPP-015 (SoD)
      - NFR-DPP-012 (SoD)
      - NFR-DPP-002 (Auditability)
      - TDD catalog: TS-API-APPROVAL-003, TS-API-AUDIT-002
    """
    raise AssertionError("Implement submitter_user_id != approver_user_id rule + audit write.")


@pytest.mark.integration
@pytest.mark.frd
@pytest.mark.nfr
@pytest.mark.xfail(reason=_todo("Signature validation, evidence package, and hashing not implemented"))
def test_integration_esign_invalid_signature_hash_is_rejected_and_no_evidence_created():
    """
    Feature: report_generation + dashboard_management (approval/reporting integrity)

    Integration negative: invalid signature hash must block approval, and system must
    not create approval_records/evidence_packages/artifacts when signature integrity fails.

    Traceability:
      - FR-DPP-016 (e-sign required)
      - FR-DPP-027/FR-DPP-028 (evidence package + hashing)
      - NFR-DPP-013 (Electronic signatures)
      - NFR-DPP-004 (fail-closed transactional audit logging)
      - TDD catalog: TS-API-APPROVAL-002, TS-API-APPROVAL-005
    """
    raise AssertionError("Implement signature validation + transactional rollback behavior.")


@pytest.mark.integration
@pytest.mark.nfr
@pytest.mark.xfail(reason=_todo("Evidence checksum and audit immutability checks not implemented"))
def test_integration_tampered_evidence_checksum_detected_and_flagged():
    """
    Feature: dashboard_management (integrity monitoring)

    Integration negative: evidence package integrity must be detectable (hash mismatch)
    and handled deterministically (block retrieval or flag as integrity violation),
    with audit evidence.

    Traceability:
      - NFR-DPP-005 (Immutability)
      - NFR-DPP-007 (Legible/open formats)
      - FR-DPP-028 (hash stored with evidence)
      - TDD catalog: TS-API-EVID-001 (negative variants) + integrity expectations
    """
    raise AssertionError("Implement evidence manifest hashing and mismatch detection.")
