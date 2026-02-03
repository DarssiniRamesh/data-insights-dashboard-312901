# Data Product Publishing Backend API

FastAPI backend for GxP-compliant data product publishing workflow.

## Overview

This backend implements a comprehensive data product publishing system with:
- **Standardized data asset metadata**: title, description, owner (constrained fields)
- **Electronic signature support** (21 CFR Part 11 aligned)
- **Segregation of Duties (SoD)** enforcement
- **Comprehensive audit trail**
- **Evidence package management**
- **Quality gate validation**
- **Approval workflow with state machine**

## Terminology

**Data Asset**: The standard term for what was previously called "submission". A data asset represents a versioned data product package with standardized metadata.

**Metadata Fields** (standardized and constrained):
- `title`: Required, 1-200 characters - The display name of the data asset
- `description`: Optional, max 2000 characters - Detailed description
- `owner`: Required, 1-120 characters - Owner identifier (email, username, or ID)

Extra fields are rejected with a 422 validation error.

## API Endpoints

### Data Assets (Primary)

**POST /api/v1/data-assets**
- Create a data asset with standardized metadata
- Requires: `draft_id`, `metadata` (title, description, owner), `audit_context`
- Returns: `data_asset_id`, metadata fields, state, timestamps

**GET /api/v1/data-assets/{data_asset_id}**
- Retrieve data asset details
- Returns: Full data asset with metadata, state, validation status

**POST /api/v1/data-assets/{data_asset_id}/validate**
- Trigger validation run
- Executes quality gates and generates validation report

**POST /api/v1/data-assets/{data_asset_id}/approve**
- Approve or reject with e-signature
- Enforces SoD (approver ≠ submitter)
- Creates evidence package on approval

### Submissions (Deprecated - Backward Compatibility)

**POST /api/v1/submissions**
- DEPRECATED: Use `/api/v1/data-assets` instead
- Maintains backward compatibility with default metadata

**GET /api/v1/submissions/{submission_id}**
- DEPRECATED: Use `/api/v1/data-assets/{id}` instead

All submission endpoints return `X-API-Deprecated` headers.

### Authentication

**POST /api/v1/auth/register**
- Register a new user
- Requires: username, password, roles

**POST /api/v1/auth/login**
- Login and receive bearer token
- Returns: access_token, expires_in

**GET /api/v1/auth/me**
- Get current user profile

### Validation

**GET /api/v1/validation-runs/{validation_run_id}**
- Retrieve validation report
- Returns: checks, overall_status, report_hash

### Audit

**GET /api/v1/audit/events**
- Query audit events (auditor/admin only)
- Filters: entity_type, entity_id, limit

### Evidence

**GET /api/v1/evidence-packages/{evidence_package_id}**
- Retrieve evidence package with integrity verification
- Returns: minted_identifier, artifacts, hashes

## Database Schema

### Core Tables

**data_assets** (formerly submissions)
- `data_asset_id` (PK)
- `title` (required, 1-200 chars, validated)
- `description` (optional, max 2000 chars)
- `owner` (required, 1-120 chars, validated)
- `state`, `package_id`, `package_version`
- Foreign keys: `draft_id`, `submitter_user_id`

**submissions** (view)
- Backward compatibility view over data_assets
- Maps `data_asset_id` → `submission_id`

**validation_runs**
- Links to `data_asset_id` (was `submission_id`)
- Stores validation results and report hashes

**approval_records**
- Links to `data_asset_id` (was `submission_id`)
- Stores e-signatures and decisions

**evidence_packages**
- Links to `data_asset_id` (was `submission_id`)
- Minted identifiers and manifest hashes

## Environment Variables

- `SQLITE_DB_PATH`: Database file path (default: `data/app.db`)
- `AUTH_ALLOW_REGISTER`: Enable/disable registration (default: true)
- `LOG_LEVEL`: Logging level (default: INFO)

## Running

```bash
# Install dependencies
pip install -r requirements.txt

# Run server
uvicorn src.api.main:app --reload --port 8000

# Run tests
pytest

# Generate coverage
pytest --cov=src --cov-report=html
```

## Deprecation Policy

**Submission endpoints** (`/api/v1/submissions/*`) are deprecated but supported for backward compatibility. All responses include deprecation headers:
- `X-API-Deprecated: true`
- `X-API-Deprecation-Message: Use /api/v1/data-assets endpoints instead`

Clients should migrate to `/api/v1/data-assets` endpoints.

## Functional Requirements

See `kavia-docs/FUNCTIONAL_REQUIREMENTS.md` for detailed GxP requirements mapping.

## Test Requirements

See `kavia-docs/TEST_REQUIREMENTS_MAP.md` for test coverage and traceability.
