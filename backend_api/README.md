# Backend API - Data Product Publishing System

## Overview

FastAPI-based backend service implementing a GxP-compliant data product publishing workflow with:
- Electronic signature support (21 CFR Part 11 aligned)
- Segregation of Duties (SoD) enforcement
- Comprehensive audit trail
- Evidence package management with cryptographic hashing
- Quality gate validation
- Approval workflow with state machine

## GxP Compliance Scope

This service is designed to meet Good Practice (GxP) regulatory requirements for electronic records and electronic signatures in regulated industries:

### Regulatory Alignment

- **21 CFR Part 11** (FDA Electronic Records and Electronic Signatures)
  - §11.10(a): User identity validation
  - §11.10(d): Secure, computer-generated audit trails
  - §11.10(e): Audit trail generation and preservation
  - §11.10(g): Authority checks and access controls
  - §11.50: Signature manifestations
  - §11.100(a): Unique user identification
  - §11.200(a)(1): Two components of identification

- **EU Annex 11** (Computerised Systems)
  - Data integrity principles (ALCOA+: Attributable, Legible, Contemporaneous, Original, Accurate)
  - Audit trail requirements
  - Electronic signature controls
  - Access control and segregation of duties

### GxP Features

1. **Electronic Signatures**: All critical decisions require electronic signature with:
   - Identity binding (signer must be authenticated user)
   - Timestamp validation (within configurable window)
   - Password reauthentication support
   - Signature hash for non-repudiation

2. **Audit Trail**: Comprehensive, tamper-evident audit logging:
   - All actions logged with actor, timestamp, correlation ID
   - Append-only design ensures immutability
   - Restricted query access (auditor/admin only)

3. **Segregation of Duties**: Enforced at workflow level:
   - Submitter cannot approve own submission
   - Role-based access control for all operations

4. **Evidence Packages**: Tamper-evident evidence creation:
   - SHA-256 cryptographic hashing
   - Integrity verification on retrieval
   - Linked to approval records via audit trail

5. **Validation & Quality Gates**: Automated validation with blocking:
   - Cannot progress workflow if validation fails
   - Validation reports are tamper-evident (hashed)

## Functional Requirements (FR) Implemented

### Authentication & Authorization
- **FR-AUTH-001**: User authentication via secure token-based mechanism
- **FR-AUTH-002**: Role-based access control (RBAC)
- **FR-AUTH-003**: User registration management with admin controls

### Data Product Submission
- **FR-DPP-001**: Dataset submission for approval workflow
- **FR-DPP-003**: Identity capture for all submissions

### Validation & Quality Gates
- **FR-VAL-001**: Automated quality gate validation
- **FR-VAL-002**: Tamper-evident validation report generation
- **FR-VAL-003**: Validation failure blocking

### Approval Workflow
- **FR-APR-001**: Electronic signature requirement
- **FR-APR-002**: Segregation of Duties (SoD) enforcement
- **FR-APR-003**: Signature identity binding
- **FR-APR-004**: Signature timestamp validation
- **FR-APR-005**: Password reauthentication for e-signatures

### Audit Trail
- **FR-AUD-001**: Comprehensive audit logging
- **FR-AUD-002**: Audit trail immutability
- **FR-AUD-003**: Audit query access control

### Evidence Packages
- **FR-EVD-001**: Evidence package creation on approval
- **FR-EVD-002**: Cryptographic hashing (SHA-256)
- **FR-EVD-003**: Evidence integrity verification
- **FR-EVD-004**: Evidence-approval linkage

### System Health
- **FR-SYS-001**: Health check endpoint
- **FR-SYS-002**: Readiness check with database validation

## FR-ID to Code Traceability

### Core Services (src/services/)

#### `auth.py` - Authentication & Authorization Service
- FR-AUTH-001: `authenticate_user()`, `create_token()`, `decode_token()`
- FR-AUTH-002: `require_roles()` dependency, RBAC enforcement
- FR-AUTH-003: `create_user()`, `set_registration_enabled()`
- FR-APR-002: `enforce_sod()` - SoD violation detection
- NFR-SEC-001: `create_token()` - HMAC-SHA256 token signing
- NFR-SEC-002: `hash_password()` - PBKDF2-HMAC-SHA256 with 100k iterations

#### `validation.py` - Validation Service
- FR-VAL-001: `run_validation()` - Executes quality gates
- FR-VAL-002: `run_validation()` - Creates hashed validation reports
- FR-VAL-003: State transition logic (pass→in_review, fail→failed_validation)
- FR-EVD-002: `run_validation()` - Computes SHA-256 of validation reports

#### `approval.py` - Approval Service
- FR-APR-001: `approve_submission()` - Requires signature block
- FR-APR-002: `approve_submission()` - Checks submitter != approver
- FR-APR-003: `approve_submission()` - Validates signer_user_id == actor
- FR-APR-004: `approve_submission()` - Validates signature timestamp window
- FR-APR-005: `approve_submission()` - Verifies password for e-sign
- FR-VAL-003: `approve_submission()` - Blocks if validation failed
- FR-EVD-001: `approve_submission()` - Creates evidence package on publish

#### `audit.py` - Audit Service
- FR-AUD-001: `record_event()` - Logs all critical actions
- FR-AUD-002: Append-only insert design ensures immutability
- FR-AUD-003: `query_events()` - Used by restricted audit router

#### `evidence.py` - Evidence Package Service
- FR-EVD-001: `create_evidence_package()` - Creates tamper-evident packages
- FR-EVD-002: `create_evidence_package()` - SHA-256 hashing of artifacts
- FR-EVD-003: `get_evidence_package()` - Verifies integrity on retrieval
- FR-EVD-004: `link_evidence_to_approval()` - Audit trail linkage

#### `submission.py` - Submission Service
- FR-DPP-001: `create_submission()` - Submission creation
- FR-DPP-003: Records submitter_user_id for identity capture

### API Routers (src/api/routers/)

#### `auth.py` - Authentication Router
- FR-AUTH-001: `/api/v1/auth/login` - User login endpoint
- FR-AUTH-002: `/api/v1/auth/assign-role` - Role assignment (admin only)
- FR-AUTH-003: `/api/v1/auth/register`, `/api/v1/auth/toggle-registration`

#### `submissions.py` - Submissions Router
- FR-DPP-001: `POST /api/v1/submissions` - Create submission
- FR-DPP-003: Extracts actor_user_id from authenticated user
- FR-VAL-001: `POST /api/v1/submissions/{id}/validate` - Trigger validation
- FR-APR-001: `POST /api/v1/submissions/{id}/approve` - Approval with signature
- FR-APR-002: Enforces SoD via ApprovalService
- FR-AUTH-001: All endpoints require authentication
- FR-AUTH-002: Role checks via get_current_user_dep

#### `validation.py` - Validation Router
- FR-VAL-002: `GET /api/v1/validation-runs/{id}` - Retrieve validation report

#### `audit.py` - Audit Router
- FR-AUD-003: `GET /api/v1/audit/events` - Restricted to auditor/admin roles

#### `evidence.py` - Evidence Router
- FR-EVD-003: `GET /api/v1/evidence-packages/{id}` - Retrieve with integrity check

### Health & Monitoring (src/api/main.py)
- FR-SYS-001: `GET /` and `GET /health` - Fast liveness probes
- FR-SYS-002: `GET /ready` - Readiness probe with database check

## Test Coverage & Traceability

### Test Organization

Tests are organized by feature under `tests/backend_api/`:

```
tests/backend_api/
├── dataset_upload/           # FR-DPP-001 related
│   └── test_dataset_upload_skeleton.py
├── report_generation/        # FR-VAL-* related
│   ├── test_report_generation_skeleton.py
│   └── test_data_product_publishing_e2e.py
└── dashboard_management/     # FR-AUTH, FR-APR, FR-AUD, FR-SYS
    ├── test_health.py
    ├── test_data_product_publishing_api_contract.py
    └── test_auth_sod_esign_negative_e2e.py
```

### FR to Test Mapping

Detailed mapping in `kavia-docs/TEST_REQUIREMENTS_MAP.md`.

#### Authentication & Authorization Tests
- FR-AUTH-001: `test_auth_missing_token_rejected_401`, `test_auth_invalid_or_expired_token_rejected_401`
- FR-AUTH-002: `test_authz_publisher_cannot_access_audit_events_403`
- FR-AUTH-003: Backend integration tests (registration flow)

#### Data Product Submission Tests
- FR-DPP-001: `test_api_create_submission_returns_201`
- FR-DPP-003: `test_auth_missing_token_rejected_401` (identity must be captured)

#### Validation Tests
- FR-VAL-001: `test_api_run_quality_gates_blocks_on_failure`
- FR-VAL-002: Backend validation report tests
- FR-VAL-003: `test_quality_gate_failed_blocks_workflow_progression` (xfail - TODO)

#### Approval Workflow Tests
- FR-APR-001: `test_esign_missing_signature_block_rejected` (xfail - TODO)
- FR-APR-002: `test_sod_same_user_cannot_submit_and_approve_same_submission` (xfail - TODO)
- FR-APR-003: `test_esign_mismatched_signer_id_rejected` (xfail - TODO)
- FR-APR-004: `test_esign_timestamp_outside_allowed_window_rejected` (xfail - TODO)
- FR-APR-005: Backend integration tests

#### Audit & Evidence Tests
- FR-AUD-001: All tests validate audit_context presence
- FR-AUD-003: `test_authz_publisher_cannot_access_audit_events_403`
- FR-EVD-002, FR-EVD-003: `test_audit_or_evidence_checksum_tampering_detected` (xfail - TODO)

#### System Health Tests
- FR-SYS-001: `test_health_check_root_returns_healthy`
- FR-SYS-002: Backend readiness tests

### Test Execution

#### Prerequisites

```bash
cd backend_api
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### Run All Tests

```bash
pytest
```

#### Run Specific Feature Tests

```bash
# Dashboard management (health, auth, approvals)
pytest tests/backend_api/dashboard_management/ -v

# Report generation (validation)
pytest tests/backend_api/report_generation/ -v

# Dataset upload
pytest tests/backend_api/dataset_upload/ -v
```

#### Run Tests by FR Marker

```bash
# Functional requirement tests
pytest -m frd -v

# Non-functional requirement tests
pytest -m nfr -v

# API contract tests
pytest -m api -v
```

#### Generate Coverage Report

```bash
pytest --cov=src --cov-report=html --cov-report=term
# View coverage report: open htmlcov/index.html
```

#### Run Tests with Detailed Output

```bash
pytest -vv --tb=short
```

### Test Artifacts & Evidence

Test execution produces evidence artifacts stored in `data/artifacts/`:

- **Validation Reports**: `data/artifacts/validation-reports/{submission_id}/{validation_run_id}.json`
- **Evidence Manifests**: `data/artifacts/evidence-manifests/{submission_id}/{evidence_package_id}.json`
- **Evidence Items**: `data/artifacts/evidence/{submission_id}/{evidence_package_id}-{idx}.json`

All artifacts are cryptographically hashed (SHA-256) for tamper detection.

## API Documentation

Interactive API documentation available at:
- Swagger UI: `http://localhost:3001/docs`
- ReDoc: `http://localhost:3001/redoc`
- OpenAPI JSON: `http://localhost:3001/openapi.json`

## Environment Configuration

Key environment variables:

```bash
# Authentication
AUTH_SECRET_KEY=<secret-key-for-token-signing>
TOKEN_EXPIRY_MINUTES=60
AUTH_ALLOW_REGISTER=true  # Allow user registration

# Database
DATABASE_PATH=data/app.db  # SQLite database path

# Artifacts
ARTIFACT_STORE_ROOT=data/artifacts  # Evidence storage root
```

## Architecture

### Database Schema

- **users**: User accounts with role assignments
- **drafts**: Draft data product packages
- **submissions**: Submission workflow records
- **validation_runs**: Validation execution records
- **approval_records**: Approval decisions with signatures
- **evidence_packages**: Evidence package metadata
- **artifacts**: Artifact storage references with hashes
- **audit_events**: Comprehensive audit trail

### Workflow State Machine

```
draft → validating → in_review → approved → published
                   ↓               ↓
              failed_validation  rejected
                   ↓
              remediating
```

## Security Considerations

1. **Token Management**: HMAC-SHA256 signed tokens; SECRET_KEY must be securely managed
2. **Password Storage**: PBKDF2-HMAC-SHA256 with 100,000 iterations
3. **Audit Trail**: Fail-closed design - if audit logging fails, transaction rolls back
4. **Evidence Integrity**: All artifacts hashed; retrieval verifies integrity

## Pending Implementation (xfail Tests)

Several GxP-critical features have test coverage but are marked `xfail` pending full implementation:

- Full SoD enforcement with identity binding across all endpoints
- Signature hash verification in all approval paths
- Signature timestamp window enforcement
- Cross-role impersonation prevention
- Evidence checksum tampering detection endpoint

See test files for detailed `TODO` annotations.

## Contributing

When adding new features:
1. Add FR-ID to `kavia-docs/FUNCTIONAL_REQUIREMENTS.md`
2. Add inline FR-ID comment in relevant code files
3. Create tests with FR-ID traceability in docstrings
4. Update this README's traceability section
5. Update `kavia-docs/TEST_REQUIREMENTS_MAP.md`

## References

- GxP Functional Requirements: `kavia-docs/FUNCTIONAL_REQUIREMENTS.md`
- Test Requirements Map: `kavia-docs/TEST_REQUIREMENTS_MAP.md`
- API Specification: `interfaces/openapi.json`
