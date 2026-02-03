# Functional Requirements - Data Product Publishing System

## Terminology

**Data Asset**: A versioned data product package with standardized metadata (title, description, owner). Formerly called "submission".

## Metadata Standards

All data assets must include exactly three metadata fields:
- **title**: Required, 1-200 characters, unique identifier/display name
- **description**: Optional, max 2000 characters, detailed information
- **owner**: Required, 1-120 characters, owner identifier (email, username, or ID)

Extra fields are rejected to enforce standardization.

## FR-001: Data Asset Creation
**ID**: FR-DAT-001 (formerly FR-SUB-001)
**Description**: Users shall be able to create data assets from approved drafts with standardized metadata
**Priority**: High
**Acceptance Criteria**:
- Data asset requires: draft_id, title (1-200 chars), owner (1-120 chars)
- Description is optional (max 2000 chars)
- Extra metadata fields are rejected with 422 error
- Data asset creation triggers automatic validation
- Audit trail records data asset creation with metadata

## FR-002: Draft Management
**ID**: FR-DRF-001
**Description**: Users shall be able to create and manage draft data product packages before data asset creation
**Priority**: High
**Acceptance Criteria**:
- Drafts can be created with full package definition
- Drafts are isolated from published data assets
- Drafts can be promoted to data assets

## FR-003: Validation Pipeline
**ID**: FR-VAL-001
**Description**: System shall execute automated validation checks on data assets
**Priority**: High
**Acceptance Criteria**:
- Metadata completeness check (title, owner required)
- State validity check
- Schema validation (if applicable)
- Validation results stored with tamper-evident hashes
- Overall status: pass/fail

## FR-004: Electronic Signatures
**ID**: FR-SIG-001
**Description**: System shall support 21 CFR Part 11 aligned electronic signatures
**Priority**: Critical
**Acceptance Criteria**:
- Signature requires: signer_user_id, signer_role, reauthentication method
- Password reauthentication validated against user credentials
- MFA/SSO reauthentication supported
- Signature reason required
- Signature hash computed and stored

## FR-005: Segregation of Duties
**ID**: FR-SOD-001
**Description**: System shall enforce Segregation of Duties: approver must not be submitter
**Priority**: Critical
**Acceptance Criteria**:
- Approval rejected if approver == submitter
- 403 Forbidden response with SoD violation error
- Audit trail records SoD checks

## FR-006: Approval Workflow
**ID**: FR-APP-001
**Description**: Data assets shall require approval before publication
**Priority**: High
**Acceptance Criteria**:
- Approval requires: decision (publish/reject), e-signature, audit context
- Validation must pass before approval (if preconditions specified)
- Evidence package generated on approval
- State transitions: in_review → published/rejected

## FR-007: Evidence Packages
**ID**: FR-EVD-001
**Description**: System shall generate tamper-evident evidence packages on approval
**Priority**: High
**Acceptance Criteria**:
- Evidence package includes: validation reports, approval records, signatures
- Minted identifier format: EVD-{package_id}-{version}
- Manifest with cryptographic hashes for all artifacts
- Integrity verification on retrieval

## FR-008: Audit Trail
**ID**: FR-AUD-001
**Description**: System shall maintain comprehensive audit trail for all actions
**Priority**: Critical
**Acceptance Criteria**:
- All data asset operations audited: create, validate, approve, reject, publish
- Audit events include: actor, role, timestamp, correlation_id, result
- Audit queries restricted to auditor/admin roles
- Immutable audit records (append-only)

## FR-009: Authentication & Authorization
**ID**: FR-AUTH-001
**Description**: System shall authenticate users and enforce role-based access
**Priority**: Critical
**Acceptance Criteria**:
- User registration with username, password, roles
- Password hashing with salt (bcrypt/argon2)
- Bearer token authentication
- Role-based endpoint access control
- Roles: publisher, steward, governance_admin, auditor, system

## FR-010: State Machine
**ID**: FR-STM-001
**Description**: Data assets shall follow defined state transitions
**Priority**: High
**Acceptance Criteria**:
- States: validating, failed_validation, in_review, remediating, approved, published, rejected
- Valid transitions enforced
- State changes audited
- Invalid transitions rejected with 409 Conflict

## FR-011: Backward Compatibility
**ID**: FR-COM-001
**Description**: System shall support legacy "submission" terminology for backward compatibility
**Priority**: Medium
**Acceptance Criteria**:
- `/api/v1/submissions/*` endpoints redirect to data asset operations
- Deprecation headers returned: X-API-Deprecated, X-API-Deprecation-Message
- Database view `submissions` maps to `data_assets` table
- Legacy tests pass without modification

## FR-012: Metadata Validation
**ID**: FR-META-001
**Description**: System shall enforce metadata field constraints
**Priority**: High
**Acceptance Criteria**:
- Title: required, 1-200 characters, non-empty after trim
- Description: optional, max 2000 characters
- Owner: required, 1-120 characters, non-empty after trim
- Extra fields rejected with 422 Unprocessable Entity
- Pydantic models use `extra='forbid'` configuration

## Traceability Matrix

| FR-ID | Implementation | Test Coverage |
|-------|---------------|---------------|
| FR-DAT-001 | `services/data_asset.py::create_data_asset` | `test_data_asset_creation_*` |
| FR-DRF-001 | `services/draft.py::create_draft` | `test_draft_*` |
| FR-VAL-001 | `services/validation.py::execute_validation_run` | `test_validation_*` |
| FR-SIG-001 | `services/approval.py::verify_electronic_signature` | `test_esign_*` |
| FR-SOD-001 | `services/approval.py::enforce_segregation_of_duties` | `test_sod_*` |
| FR-APP-001 | `services/approval.py::process_approval` | `test_approval_*` |
| FR-EVD-001 | `services/evidence.py::create_evidence_package` | `test_evidence_*` |
| FR-AUD-001 | `services/audit.py::record_event` | `test_audit_*` |
| FR-AUTH-001 | `services/auth.py` | `test_auth_*` |
| FR-STM-001 | `services/data_asset.py::update_state` | `test_state_machine_*` |
| FR-COM-001 | `routers/submissions.py` | `test_backward_compat_*` |
| FR-META-001 | `schemas/__init__.py::DataAssetMetadata` | `test_metadata_validation_*` |
