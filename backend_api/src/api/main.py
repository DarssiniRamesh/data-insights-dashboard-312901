"""
FastAPI application for data product publishing workflow.

This application implements a GxP-compliant data product publishing system with:
- Electronic signature support (21 CFR Part 11 aligned)
- Segregation of Duties (SoD) enforcement
- Comprehensive audit trail
- Evidence package management
- Quality gate validation
- Approval workflow with state machine
- Standardized data asset metadata (title, description, owner)

Real-time WebSocket endpoints (planned):
- Connection: ws://host/ws/data-assets/{data_asset_id}/status
  Subscribe to real-time data asset state updates
- Connection: ws://host/ws/validation/{validation_run_id}/progress
  Subscribe to real-time validation progress updates

For WebSocket usage examples, see the /docs/websocket-usage endpoint.

Terminology: 'data asset' (formerly 'submission') with standardized metadata fields.
"""
from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException as FastAPIHTTPException

# Ensure we emit useful startup diagnostics in preview/CI even if no logging is configured.
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

logger = logging.getLogger("backend_api")

# Support both launch modes:
#  - uvicorn api.main:app (pythonpath includes "src")
#  - uvicorn src.api.main:app (imports as a package)
try:
    from .routers import drafts, submissions, data_assets, validation, audit, evidence, auth, submissions_compat
    from ..database import init_db, seed_test_users, db_status
except ImportError:  # pragma: no cover
    from api.routers import drafts, submissions, data_assets, validation, audit, evidence, auth, submissions_compat
    from database import init_db, seed_test_users, db_status


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events.

    Startup behavior requirements:
    - Initialize DB schema and seed required users (including 'system') if possible.
    - Never crash the server if DB is misconfigured/unavailable; run in degraded mode.
    """
    # Startup
    app.state.db_initialized = False
    app.state.db_seeded = False

    try:
        init_db()
        app.state.db_initialized = True
        logger.info("Database schema initialization completed.")
    except Exception:
        # Non-fatal: boot should not be blocked by DB issues.
        logger.exception("Database initialization failed; continuing to boot (degraded mode).")

    # Seed only if init_db succeeded (avoids confusing cascaded errors).
    if app.state.db_initialized:
        try:
            seed_test_users()
            app.state.db_seeded = True
            logger.info("Database seeding completed.")
        except Exception:
            logger.exception("Database seeding failed; continuing to boot (degraded mode).")

    yield

    # Shutdown (if needed in future)
    pass

# OpenAPI metadata
openapi_tags = [
    {
        "name": "auth",
        "description": "Authentication and authorization endpoints. Provides login, registration, role assignment, and user profile retrieval."
    },
    {
        "name": "drafts",
        "description": "Draft data product package management. Allows publishers to create and manage draft packages before data asset creation."
    },
    {
        "name": "data-assets",
        "description": "Data asset workflow management with standardized metadata (title, description, owner). Includes creation, validation triggering, and approval/rejection. Enforces SoD and e-sign requirements."
    },
    {
        "name": "submissions",
        "description": "DEPRECATED: Legacy submission endpoints for backward compatibility (deprecated, use data asset). Use data-assets endpoints instead. Submission workflow management including creation, validation triggering, and approval/rejection."
    },
    {
        "name": "validation",
        "description": "Validation report retrieval. Provides access to quality gate execution results and validation evidence."
    },
    {
        "name": "audit",
        "description": "Audit trail queries. Restricted to auditor and governance_admin roles for compliance."
    },
    {
        "name": "evidence",
        "description": "Evidence package retrieval with integrity verification. Provides tamper-evident audit evidence packages."
    }
]

app = FastAPI(
    title="Data Product Publishing API",
    description=__doc__,
    version="1.0.0",
    openapi_tags=openapi_tags,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware
#
# IMPORTANT:
# - Browsers reject CORS responses that combine `Access-Control-Allow-Origin: *`
#   with `Access-Control-Allow-Credentials: true`.
# - Our frontend runs on a separate origin (e.g., :3000), so we must echo an
#   explicit allowed origin for both preflight (OPTIONS) and actual requests.
#
# Configuration:
# - BACKEND_CORS_ALLOW_ORIGINS (optional): comma-separated list of additional
#   allowed origins. Example:
#   BACKEND_CORS_ALLOW_ORIGINS=https://example.com,https://staging.example.com
#
# NOTE (Kavia preview environments):
# The preview frontend origin can change between sessions (dynamic subdomain),
# so we support it via a constrained regex rather than a single hardcoded host.
default_allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://localhost:3000",
    "https://127.0.0.1:3000",
]

extra_origins_env = os.getenv("BACKEND_CORS_ALLOW_ORIGINS", "").strip()
extra_allowed_origins = [o.strip() for o in extra_origins_env.split(",") if o.strip()]

allowed_origins = [*default_allowed_origins, *extra_allowed_origins]

# Allow Kavia preview origins like:
#   https://vscode-internal-17389-beta.beta01.cloud.kavia.ai:3000
#
# Preview environments can vary by session and sometimes by port, so we:
#  - support a constrained default regex for Kavia preview domains
#  - allow overriding via BACKEND_CORS_ALLOW_ORIGIN_REGEX when needed
#
# This ensures preflight (OPTIONS) for endpoints like /api/v1/auth/login returns
# Access-Control-Allow-Origin for the current preview host.
_default_kavia_preview_origin_regex = (
    r"^https?://vscode-internal-[a-zA-Z0-9-]+\.beta01\.cloud\.kavia\.ai(:\d+)?$"
)
kavia_preview_origin_regex = os.getenv(
    "BACKEND_CORS_ALLOW_ORIGIN_REGEX",
    _default_kavia_preview_origin_regex,
).strip()

# If the environment can provide the exact preview origin, add it explicitly to
# allow_origins. This avoids edge-case mismatches in origin parsing/normalization
# through proxies and guarantees CORSMiddleware will echo it on preflight.
preview_origin = os.getenv("BACKEND_CORS_PREVIEW_ORIGIN", "").strip()
if preview_origin:
    allowed_origins = [*allowed_origins, preview_origin]

# Only allow credentials when we are NOT using wildcard origins.
# (We currently do not use wildcard, but this protects future edits.)
allow_credentials = "*" not in allowed_origins

logger.info(
    "CORS configured. allow_origins=%s allow_origin_regex=%s allow_credentials=%s",
    allowed_origins,
    kavia_preview_origin_regex,
    allow_credentials,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=kavia_preview_origin_regex,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Some proxies / error paths can yield responses without CORSMiddleware-applied headers,
# especially for unhandled exceptions or non-standard error responses.
# This middleware is a minimal defensive layer to ensure:
#  - Preflight (OPTIONS) always returns a sane response
#  - CORS headers are present whenever an allowed Origin is provided


@app.middleware("http")
async def ensure_cors_headers(request: Request, call_next):
    """
    Ensure CORS headers are present on all responses (including error paths).

    Why:
      - Browsers require Access-Control-Allow-Origin for both preflight and actual requests.
      - Some failure responses (500s, proxy-generated errors) can surface without CORS headers.
      - This middleware provides a safe fallback that does not expand allowed origins beyond
        the CORSMiddleware configuration.

    Behavior:
      - Do NOT short-circuit OPTIONS (CORSMiddleware should handle preflight).
      - Call downstream handlers, then add ACAO if missing and origin is allowed.
    """
    origin = request.headers.get("origin")

    resp = await call_next(request)

    if not origin:
        return resp

    # If CORSMiddleware already set headers, do nothing.
    if "access-control-allow-origin" in (k.lower() for k in resp.headers.keys()):
        return resp

    # Only echo back origins we already consider allowed (do not widen policy).
    origin_allowed = origin in allowed_origins
    if not origin_allowed:
        # Regex support (same as CORSMiddleware)
        import re

        try:
            origin_allowed = bool(re.match(kavia_preview_origin_regex, origin))
        except re.error:
            origin_allowed = False

    if origin_allowed:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        if allow_credentials:
            resp.headers["Access-Control-Allow-Credentials"] = "true"

    return resp


def _apply_cors_headers_if_allowed(request: Request, response: Response) -> Response:
    """
    Apply CORS response headers if request Origin is allowed and headers are not already set.

    Note: This is used by exception handlers because FastAPI can generate error responses
    outside the normal middleware response path, which may omit ACAO and break the frontend.
    """
    origin = request.headers.get("origin")
    if not origin:
        return response

    if "access-control-allow-origin" in (k.lower() for k in response.headers.keys()):
        return response

    origin_allowed = origin in allowed_origins
    if not origin_allowed:
        import re

        try:
            origin_allowed = bool(re.match(kavia_preview_origin_regex, origin))
        except re.error:
            origin_allowed = False

    if origin_allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        if allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"

    return response


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException):
    """
    Ensure HTTPException responses include CORS headers when Origin is allowed.

    This prevents the browser from hiding useful error details and blocking the dashboard
    when an endpoint returns 4xx (or explicitly raised 5xx) responses.
    """
    response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return _apply_cors_headers_if_allowed(request, response)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Ensure unhandled 500 responses include CORS headers when Origin is allowed.

    We intentionally do not leak exception details to clients.
    """
    logger.exception("Unhandled exception: %s", exc)
    response = JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
    return _apply_cors_headers_if_allowed(request, response)


# Register routers
app.include_router(auth.router)
app.include_router(drafts.router)
app.include_router(data_assets.router)  # New standardized endpoints
app.include_router(submissions.router)  # Backward compatibility
app.include_router(validation.router)
app.include_router(audit.router)
app.include_router(evidence.router)

# Register compatibility router (for test payloads)
app.include_router(submissions_compat.router)


# PUBLIC_INTERFACE
@app.get("/", tags=["health"], summary="Health Check", description="Liveness probe (DB-independent).")
def health_check():
    """
    Health check endpoint (liveness).

    Returns a deterministic payload without touching dependencies (e.g., DB),
    so the service can report liveness even in degraded mode.
    """
    return {"message": "Healthy"}


# PUBLIC_INTERFACE
@app.options("/health", tags=["health"], summary="Health CORS Preflight", description="CORS preflight handler for /health.")
def health_options() -> Response:
    """
    CORS preflight for /health.

    Returns:
      - 200 OK (headers added by CORS middleware / fallback middleware)
    """
    return Response(status_code=status.HTTP_200_OK)


# PUBLIC_INTERFACE
@app.get("/health", tags=["health"], summary="Health Endpoint", description="Liveness probe (DB-independent).")
def health_endpoint():
    """
    Health endpoint (liveness).

    Returns a deterministic payload and does not depend on DB connectivity.
    """
    return {"message": "Healthy"}


# PUBLIC_INTERFACE
@app.options(
    "/ready",
    tags=["health"],
    summary="Ready CORS Preflight",
    description="CORS preflight handler for /ready.",
    operation_id="readiness_options",
)
def readiness_options() -> Response:
    """
    CORS preflight for /ready.

    Returns:
      - 200 OK (headers added by CORS middleware / fallback middleware)
    """
    return Response(status_code=status.HTTP_200_OK)


# PUBLIC_INTERFACE
@app.get(
    "/ready",
    tags=["health"],
    summary="Readiness Endpoint",
    description="Readiness probe (touches DB). Returns 200 only when DB is reachable and initialized.",
    operation_id="readiness_endpoint",
)
def readiness_endpoint(request: Request):
    """
    Readiness endpoint (DB-dependent).

    This is intended for environments that want a stronger signal than /health.
    It checks whether:
      - a DB connection can be established and a trivial query succeeds, AND
      - the app successfully ran schema init during lifespan startup.

    Returns:
      - 200 when DB is reachable and initialized
      - 503 when DB is not ready
    """
    ok, path, degraded = db_status()
    initialized = bool(getattr(request.app.state, "db_initialized", False))

    if ok and initialized:
        return {
            "status": "ready",
            "db": {"ok": True, "path": path, "degraded": degraded, "initialized": initialized},
        }

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "not_ready",
            "db": {"ok": bool(ok), "path": path, "degraded": degraded, "initialized": initialized},
        },
    )


@app.get("/docs/websocket-usage", tags=["documentation"])
def websocket_usage_docs():
    """
    WebSocket usage documentation.

    This endpoint provides documentation and examples for WebSocket connections.

    Note: WebSocket endpoints are planned for future implementation to provide
    real-time updates for data asset state changes and validation progress.

    Planned WebSocket endpoints:
    - ws://host/ws/data-assets/{data_asset_id}/status

    Compatibility note:
    - ws://host/ws/submissions/{submission_id}/status (deprecated, use data asset)
    """
    return {
        "websocket_endpoints": [
            {
                "path": "ws://host/ws/data-assets/{data_asset_id}/status",
                "description": "Subscribe to real-time data asset state updates",
                "status": "planned",
            },
            {
                "path": "ws://host/ws/submissions/{submission_id}/status",
                "description": "Legacy alias (deprecated, use data asset)",
                "status": "planned",
            },
            {
                "path": "ws://host/ws/validation/{validation_run_id}/progress",
                "description": "Subscribe to real-time validation progress updates",
                "status": "planned",
            },
        ],
        "usage_example": {
            "python": """
import asyncio
import websockets

async def subscribe_to_data_asset():
    uri = "ws://localhost:3001/ws/data-assets/da-123/status"
    async with websockets.connect(uri) as websocket:
        while True:
            message = await websocket.recv()
            print(f"Status update: {message}")

asyncio.run(subscribe_to_data_asset())
            """,
            "javascript": """
const ws = new WebSocket('ws://localhost:3001/ws/data-assets/da-123/status');

ws.onmessage = (event) => {
    const update = JSON.parse(event.data);
    console.log('Status update:', update);
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
};
            """,
        },
    }


# PUBLIC_INTERFACE
def run() -> None:
    """Run the FastAPI app with Uvicorn using HOST/PORT environment variables.

    This is a convenience entrypoint for environments that launch via
    `python -m src.api.main` instead of `uvicorn ...`.

    Environment variables:
      - HOST (default: 0.0.0.0)
      - PORT (default: 3001)
      - UVICORN_WORKERS (default: 1)
      - LOG_LEVEL (default: INFO)

    Returns:
      None
    """
    import uvicorn

    host = os.getenv("HOST", os.getenv("UVICORN_HOST", "0.0.0.0"))
    port = int(os.getenv("PORT", "3001"))
    workers = int(os.getenv("UVICORN_WORKERS", "1"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()

    uvicorn.run("src.api.main:app", host=host, port=port, workers=workers, log_level=log_level)


if __name__ == "__main__":  # pragma: no cover
    run()
