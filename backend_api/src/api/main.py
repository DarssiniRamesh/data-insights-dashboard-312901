"""
FastAPI application for data product publishing workflow.

This application implements a GxP-compliant data product publishing system with:
- Electronic signature support (21 CFR Part 11 aligned)
- Segregation of Duties (SoD) enforcement
- Comprehensive audit trail
- Evidence package management
- Quality gate validation
- Approval workflow with state machine

Real-time WebSocket endpoints:
- Connection: ws://host/ws/submissions/{submission_id}/status
  Subscribe to real-time submission state updates
- Connection: ws://host/ws/validation/{validation_run_id}/progress
  Subscribe to real-time validation progress updates

For WebSocket usage examples, see the /docs/websocket-usage endpoint.
"""
from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Proxy header support:
# Starlette removed ProxyHeadersMiddleware in newer versions. Use the supported
# ForwardedHeadersMiddleware when available so the app doesn't crash at import time.
try:  # pragma: no cover
    from starlette.middleware.forwarded import ForwardedHeadersMiddleware
except Exception:  # pragma: no cover
    ForwardedHeadersMiddleware = None  # type: ignore[assignment]

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
    from .routers import drafts, submissions, validation, audit, evidence, auth, submissions_compat
    from ..database import init_db, seed_test_users, db_status
except ImportError:  # pragma: no cover
    from api.routers import drafts, submissions, validation, audit, evidence, auth, submissions_compat
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
        "description": "Draft data product package management. Allows publishers to create and manage draft packages before submission."
    },
    {
        "name": "submissions",
        "description": "Submission workflow management including creation, validation triggering, and approval/rejection. Enforces SoD and e-sign requirements."
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

# If the service is deployed behind a reverse proxy that mounts it under a path prefix
# (e.g., https://host/some/prefix -> this app), Swagger UI must request the OpenAPI
# schema from that same prefix. Configure this via ROOT_PATH.
#
# NOTE: Do not hardcode deployment paths; use env var so preview/prod can differ.
root_path = os.getenv("ROOT_PATH", "")

app = FastAPI(
    title="Data Product Publishing API",
    description=__doc__,
    version="1.0.0",
    openapi_tags=openapi_tags,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    root_path=root_path,
    lifespan=lifespan,
)

# CORS middleware
#
# IMPORTANT:
# - Browsers forbid `Access-Control-Allow-Origin: *` when `Access-Control-Allow-Credentials: true`.
#   Using allow_origins=["*"] with allow_credentials=True causes preflight/credentialed requests
#   (e.g., from the React frontend) to be blocked by the browser.
# - We therefore require explicit allowed origins and make them configurable via env var so
#   preview deployments can be added without code changes.
cors_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
allow_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]

# Must be added before other middleware so downstream URL generation uses forwarded values.
#
# NOTE: Starlette's forwarded middleware is safe to use behind a reverse proxy that
# sets Forwarded / X-Forwarded-* headers. If it's unavailable, we skip it rather than
# crashing the service (boot stability > perfect URL reconstruction).
trust_proxy = os.getenv("TRUST_PROXY", "false").strip().lower() in {"1", "true", "yes", "on"}
if trust_proxy and ForwardedHeadersMiddleware is not None:
    app.add_middleware(ForwardedHeadersMiddleware)
elif trust_proxy and ForwardedHeadersMiddleware is None:  # pragma: no cover
    logger.warning(
        "TRUST_PROXY enabled but ForwardedHeadersMiddleware is unavailable; "
        "skipping proxy header processing."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    # Include OPTIONS explicitly for clarity (preflight). "*" would also work.
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(drafts.router)
app.include_router(submissions.router)
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
@app.get("/health", tags=["health"], summary="Health Endpoint", description="Liveness probe (DB-independent).")
def health_endpoint():
    """
    Health endpoint (liveness).

    Returns a deterministic payload and does not depend on DB connectivity.
    """
    return {"message": "Healthy"}


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
    real-time updates for submission state changes and validation progress.
    
    Planned WebSocket endpoints:
    - ws://host/ws/submissions/{submission_id}/status
    - ws://host/ws/validation/{validation_run_id}/progress
    """
    return {
        "websocket_endpoints": [
            {
                "path": "ws://host/ws/submissions/{submission_id}/status",
                "description": "Subscribe to real-time submission state updates",
                "status": "planned"
            },
            {
                "path": "ws://host/ws/validation/{validation_run_id}/progress",
                "description": "Subscribe to real-time validation progress updates",
                "status": "planned"
            }
        ],
        "usage_example": {
            "python": """
import asyncio
import websockets

async def subscribe_to_submission():
    uri = "ws://localhost:8000/ws/submissions/sub-123/status"
    async with websockets.connect(uri) as websocket:
        while True:
            message = await websocket.recv()
            print(f"Status update: {message}")

asyncio.run(subscribe_to_submission())
            """,
            "javascript": """
const ws = new WebSocket('ws://localhost:8000/ws/submissions/sub-123/status');

ws.onmessage = (event) => {
    const update = JSON.parse(event.data);
    console.log('Status update:', update);
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
};
            """
        }
    }
