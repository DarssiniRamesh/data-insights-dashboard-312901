# Test Requirements Mapping

## Overview

This document maps test cases to functional requirements for the Data Product Publishing System.

**Terminology**: "Data asset" is the standard term (formerly "submission").

## Test Organization

Tests are organized by feature under `backend_api/tests/backend_api/`:
- `dataset_upload/` - Data asset intake and creation tests
- `report_generation/` - Report and evidence generation tests
- `dashboard_management/` - API contract, authentication, and workflow tests

## Feature: Data Asset Creation (FR-DAT-001)

### Test Cases

**test_data_asset_creation_with_valid_metadata**
- **FR-ID**: FR-DAT-001, FR-META-001
- **Description**: Verify data asset creation with valid standardized metadata
- **Acceptance Criteria**:
  - Title: 1-200 characters (e.g., "My Data Asset")
  - Owner: 1-120 characters (e.g., "user@example.com")
  - Description: optional, max 2000 characters
  - Returns: data_asset_id, metadata fields, state='validating'

**test_data_asset_creation_rejects_extra_fields**
- **FR-ID**: FR-META-001
- **Description**: Verify extra metadata fields are rejected
- **Acceptance Criteria**:
  - Request with extra fields (e.g., category, tags) returns 422
  - Error message indicates validation failure
  - Pydantic models use `extra='forbid'`

**test_data_asset_creation_title_length_constraints**
- **FR-ID**: FR-META-001
- **Description**: Verify title length constraints
- **Test Cases**:
  - Empty title → 422 error
  - Title > 200 chars → 422 error
  - Title = 1 char → success
  - Title = 200 chars → success

**test_data_asset_creation_owner_required**
- **FR-ID**: FR-META-001
- **Description**: Verify owner is required
- **Acceptance Criteria**:
  - Missing owner → 422 error
  - Empty owner → 422 error
  - Owner > 120 chars → 422 error

**test_data_asset_creation_description_optional**
- **FR-ID**: FR-META-001
- **Description**: Verify description is optional
- **Acceptance Criteria**:
  - Null description → success
  - Empty description → success (treated as null)
  - Description > 2000 chars → 422 error

## Feature: Validation Pipeline (FR-VAL-001)

### Test Cases

**test_validation_metadata_completeness_check**
- **FR-ID**: FR-VAL-001, FR-META-001
- **Description**: Verify validation checks metadata completeness
- **Acceptance Criteria**:
  - Check validates title present
  - Check validates owner present
  - Overall status = fail if metadata incomplete

**test_validation_generates_tamper_evident_report**
- **FR-ID**: FR-VAL-001, FR-EVD-001
- **Description**: Verify validation report is tamper-evident
- **Acceptance Criteria**:
  - Report hash (SHA-256) stored
  - Report stored with artifact record
  - Hash verification on retrieval

## Feature: Electronic Signatures (FR-SIG-001)

### Test Cases

**test_esign_password_reauthentication**
- **FR-ID**: FR-SIG-001
- **Description**: Verify password reauthentication for e-signatures
- **Acceptance Criteria**:
  - Valid password → signature accepted
  - Invalid password → 400 error
  - Missing password → 400 error

**test_esign_signature_reason_required**
- **FR-ID**: FR-SIG-001
- **Description**: Verify signature reason is required
- **Acceptance Criteria**:
  - Missing reason → 422 error
  - Signature reason stored in approval record

## Feature: Segregation of Duties (FR-SOD-001)

### Test Cases

**test_sod_violation_same_user**
- **FR-ID**: FR-SOD-001
- **Description**: Verify SoD prevents self-approval
- **Acceptance Criteria**:
  - Approver == submitter → 403 Forbidden
  - Error message indicates SoD violation
  - Audit event records SoD check with result=blocked

**test_sod_success_different_users**
- **FR-ID**: FR-SOD-001
- **Description**: Verify SoD allows approval by different user
- **Acceptance Criteria**:
  - Approver ≠ submitter → approval proceeds
  - State transitions to published/rejected

## Feature: Approval Workflow (FR-APP-001)

### Test Cases

**test_approval_requires_validation_pass**
- **FR-ID**: FR-APP-001, FR-VAL-001
- **Description**: Verify approval requires passing validation
- **Acceptance Criteria**:
  - Validation status = fail → 409 error
  - Validation status = pass → approval proceeds
  - Preconditions check validation_run_id

**test_approval_creates_evidence_package**
- **FR-ID**: FR-APP-001, FR-EVD-001
- **Description**: Verify evidence package created on approval
- **Acceptance Criteria**:
  - Decision = publish → evidence package created
  - Evidence package ID returned in response
  - Minted identifier format: EVD-{package_id}-{version}

## Feature: Evidence Packages (FR-EVD-001)

### Test Cases

**test_evidence_package_contains_all_artifacts**
- **FR-ID**: FR-EVD-001
- **Description**: Verify evidence package includes all artifacts
- **Acceptance Criteria**:
  - Includes validation reports
  - Includes approval records
  - Includes e-signatures
  - Manifest with artifact hashes

**test_evidence_package_integrity_verification**
- **FR-ID**: FR-EVD-001
- **Description**: Verify evidence package integrity on retrieval
- **Acceptance Criteria**:
  - Manifest hash verified
  - Artifact hashes verified
  - Integrity violation → 409 error

## Feature: Audit Trail (FR-AUD-001)

### Test Cases

**test_audit_data_asset_lifecycle**
- **FR-ID**: FR-AUD-001, FR-DAT-001
- **Description**: Verify audit events for data asset lifecycle
- **Acceptance Criteria**:
  - data_asset_created event recorded
  - data_asset_state_changed events recorded
  - data_asset_approved/rejected events recorded

**test_audit_query_restricted_to_auditor**
- **FR-ID**: FR-AUD-001, FR-AUTH-001
- **Description**: Verify audit queries restricted to auditor role
- **Acceptance Criteria**:
  - Auditor role → 200 OK
  - Publisher role → 403 Forbidden
  - Admin role → 200 OK (governance_admin)

## Feature: Backward Compatibility (FR-COM-001)

### Test Cases

**test_submission_endpoints_deprecated**
- **FR-ID**: FR-COM-001
- **Description**: Verify submission endpoints return deprecation headers
- **Acceptance Criteria**:
  - Response includes X-API-Deprecated: true
  - Response includes X-API-Deprecation-Message
  - Endpoints function correctly (map to data assets)

**test_submissions_view_compatibility**
- **FR-ID**: FR-COM-001
- **Description**: Verify database view provides backward compatibility
- **Acceptance Criteria**:
  - Query `SELECT * FROM submissions` succeeds
  - submission_id maps to data_asset_id
  - View includes all expected columns

## Feature: API Contract Tests

### Test Cases

**test_api_contract_data_asset_creation**
- **FR-ID**: FR-DAT-001, FR-META-001
- **Description**: Verify API contract for data asset creation endpoint
- **Path**: `POST /api/v1/data-assets`
- **Contract**:
  - Request: draft_id, metadata {title, description, owner}, audit_context
  - Response 201: data_asset_id, title, description, owner, state, timestamps
  - Response 422: validation error (metadata constraints)
  - Response 400: draft not found

**test_api_contract_data_asset_approval**
- **FR-ID**: FR-APP-001, FR-SIG-001, FR-SOD-001
- **Description**: Verify API contract for approval endpoint
- **Path**: `POST /api/v1/data-assets/{id}/approve`
- **Contract**:
  - Request: decision, signature, password, audit_context
  - Response 200: data_asset_id, state, evidence_package_id
  - Response 403: SoD violation
  - Response 400: signature verification failed
  - Response 409: validation not passed

## Test Coverage Goals

| Feature | Target Coverage | Current Status |
|---------|----------------|----------------|
| Data Asset Creation | 90% | Implemented |
| Metadata Validation | 95% | Implemented |
| Validation Pipeline | 85% | Implemented |
| E-Signatures | 90% | Implemented |
| SoD Enforcement | 95% | Implemented |
| Approval Workflow | 85% | Implemented |
| Evidence Packages | 80% | Implemented |
| Audit Trail | 85% | Implemented |
| Authentication | 90% | Implemented |
| Backward Compatibility | 80% | Implemented |

## Test Execution

```bash
# Run all tests
pytest

# Run feature-specific tests
pytest tests/backend_api/dataset_upload/
pytest tests/backend_api/dashboard_management/

# Run with coverage
pytest --cov=src --cov-report=html

# Run API contract tests only
pytest -k "api_contract"

# Run metadata validation tests
pytest -k "metadata"
```

## Traceability

All test functions include FR-ID references in docstrings for traceability:

```python
def test_data_asset_creation_with_valid_metadata():
    """
    Test data asset creation with standardized metadata.
    
    FR-DAT-001: Data asset creation
    FR-META-001: Metadata validation
    """
    # test implementation
```
