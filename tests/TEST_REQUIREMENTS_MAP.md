# Tests ↔ Requirements Map

This document maps **user-facing requirements/capabilities** to **test coverage** in this repository.

Scope (per work item):
- `dataset_upload`
- `report_generation`
- `dashboard_management`

Test suites exist in two containers:
- Backend: `data-insights-dashboard-312901/backend_api/` (pytest)
- Frontend: `data-insights-dashboard-312902/frontend_dashboard/` (Jest/React Testing Library)

## Current coverage summary (what exists today)

### Backend (FastAPI)
Existing tests prior to reorg:
- Health endpoint API tests
- OpenAPI schema generation unit test
- Data-product publishing API contract tests (submission/validation/approval/publish; many tests include `xfail` for TODO features)
- Integration tests (mostly `xfail` placeholders for workflow/auth/e-sign/SoD)

These are **closest to report_generation/dashboard_management** (validation reports, audit/evidence retrieval) rather than literal "dataset_upload".

### Frontend (React)
Existing tests prior to reorg:
- `App.test.js` verifies unauthenticated flow renders login page

This is **minimal dashboard_management/auth navigation coverage**.

---

## Requirements → Tests matrix

Legend:
- ✅ covered (implemented assertions)
- 🟡 partial/contract/smoke (basic assertions, or mostly TODO/xfail)
- ❌ missing (only skeleton placeholder tests added)

### Feature: dataset_upload

| Requirement / capability | Backend tests | Frontend tests | Status / notes |
|---|---|---|---|
| User can upload/submit a dataset (or dataset reference) | `backend_api/tests/backend_api/dataset_upload/test_dataset_upload_skeleton.py` | `tests/frontend_dashboard/dataset_upload/test_dataset_upload_skeleton.test.js` | ❌ No explicit dataset upload endpoint tests exist; current backend centers on “data product package + submission” workflows rather than file upload. Skeletons added. |
| Validation of upload payload / schema | `backend_api/tests/backend_api/dataset_upload/test_dataset_upload_skeleton.py` | `tests/frontend_dashboard/dataset_upload/test_dataset_upload_skeleton.test.js` | ❌ Skeletons added. |

### Feature: report_generation

| Requirement / capability | Backend tests | Frontend tests | Status / notes |
|---|---|---|---|
| Generate/trigger validation or report for a submission | `backend_api/tests/backend_api/report_generation/test_report_generation_skeleton.py` | `tests/frontend_dashboard/report_generation/test_report_generation_skeleton.test.js` | 🟡 Backend has validation-related endpoints in API spec, but tests are not organized by “report_generation” and are mostly workflow-contract focused. Skeletons added to anchor feature-based structure. |
| Retrieve a validation/report artifact (summary) | `backend_api/tests/backend_api/report_generation/test_report_generation_skeleton.py` | `tests/frontend_dashboard/report_generation/test_report_generation_skeleton.test.js` | 🟡 Existing contract tests touch `/api/v1/validation-runs/{id}` indirectly only; skeletons added for explicit feature grouping. |

### Feature: dashboard_management

| Requirement / capability | Backend tests | Frontend tests | Status / notes |
|---|---|---|---|
| Dashboard shows system health/readiness | `backend_api/tests/backend_api/dashboard_management/test_health.py` | (future) `tests/frontend_dashboard/dashboard_management/...` | ✅ Backend health tests exist and were moved under dashboard_management as “system status”. Frontend has a StatusBar component but no test yet (skeleton added). |
| Manage/tracking submissions in UI (add/remove/refresh) | (N/A / backend list endpoints not present) | `tests/frontend_dashboard/dashboard_management/test_app_routing_auth.test.js` + `tests/frontend_dashboard/dashboard_management/test_dashboard_skeleton.test.js` | 🟡 App auth routing test exists (moved). Dashboard behaviors are currently untested; skeleton added. |
| Audit/event viewing & evidence retrieval (dashboard admin) | Existing backend API contract tests cover auth/audit/evidence endpoints at a contract level: `backend_api/tests/backend_api/dashboard_management/test_data_product_publishing_api_contract.py` | (future) skeleton | 🟡 Backend contract tests include audit/evidence access expectations; many are TODO/xfail. Skeleton added for frontend. |

---

## Gaps (recommended next real tests to implement)

1. **dataset_upload**
   - Backend: add API tests once an upload endpoint exists (multipart file upload or dataset reference creation endpoint).
   - Frontend: add component tests for upload form + success/error states.

2. **report_generation**
   - Backend: add tests that create a submission/draft via real API and then trigger validation and fetch report summary.
   - Frontend: add tests for Validation page interactions (mock API client).

3. **dashboard_management**
   - Frontend: add tests for `DashboardPage` localStorage tracking (`submissionStore`) and refresh/remove actions.
   - Backend: expand readiness tests and role-based access tests when auth is fully enforced (many are currently xfail).

"
