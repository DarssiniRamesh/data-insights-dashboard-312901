# Tests

This repository is a multi-container project with:

- `backend_api` (FastAPI, Python/pytest)
- `frontend_dashboard` (React, Jest via `react-scripts`)

The tests are organized by container and then by feature:

- `tests/backend_api/<feature>/...`
- `tests/frontend_dashboard/<feature>/...`

## Backend (FastAPI) tests

**Location:** `data-insights-dashboard-312901/backend_api/`

### Run all backend tests

```bash
cd data-insights-dashboard-312901/backend_api
pytest
```

### Run a subset (by folder)

```bash
cd data-insights-dashboard-312901/backend_api
pytest tests/backend_api/dataset_upload
pytest tests/backend_api/report_generation
pytest tests/backend_api/dashboard_management
```

### Notes

- Test discovery/config is controlled by `backend_api/pytest.ini` (`testpaths = tests`).
- `backend_api/tests/conftest.py` configures an isolated SQLite DB per test session and provides `async_client` for API tests.

## Frontend (React) tests

**Location:** `data-insights-dashboard-312902/frontend_dashboard/`

### Run all frontend tests (non-interactive / CI mode)

`react-scripts test` is interactive by default. Use CI mode:

```bash
cd data-insights-dashboard-312902/frontend_dashboard
CI=true npm test -- --watchAll=false
```

### Run a subset (pattern)

```bash
cd data-insights-dashboard-312902/frontend_dashboard
CI=true npm test -- --watchAll=false --testPathPattern=dataset_upload
```

### Notes

- Jest is configured by Create React App conventions; tests are discovered from:
  - `src/**/?(*.)+(spec|test).(js|jsx|ts|tsx)`
  - `__tests__` folders
- `src/setupTests.js` configures `@testing-library/jest-dom`.

## Feature mapping used in this repo

The work item features are mapped as follows:

- `dataset_upload`: dataset ingestion/upload flows (UI form + backend endpoint)
- `report_generation`: generating/triggering validation, reports, or exports
- `dashboard_management`: dashboard UI state, tracked items, management actions

If your implementation uses different feature boundaries, update the mapping document at:
`data-insights-dashboard-312901/tests/TEST_REQUIREMENTS_MAP.md`.
