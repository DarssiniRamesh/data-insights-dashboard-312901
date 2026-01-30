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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("backend_api")

# Support both launch modes:
#  - uvicorn api.main:app (pythonpath includes "src")
#  - uvicorn src.api.main:app (imports as a package)
try:
    from .routers import drafts, submissions, validation, audit, evidence, auth, submissions_compat
    from ..database import init_db, seed_test_users
except ImportError:  # pragma: no cover
    from api.routers import drafts, submissions, validation, audit, evidence, auth, submissions_compat
    from database import init_db, seed_test_users


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    try:
        init_db()
        seed_test_users()
        logger.info("Database initialization and seeding completed.")
    except Exception:
        # Non-fatal: boot should not be blocked by non-critical DB issues.
        logger.exception("Database initialization failed; continuing to boot (endpoints may error).")

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
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


@app.get("/", tags=["health"])
def health_check():
    """
    Health check endpoint.
    
    Returns basic health status for readiness probes.
    """
    return {"message": "Healthy"}


@app.get("/health", tags=["health"])
def health_endpoint():
    """
    Health check endpoint.
    
    Returns basic health status for readiness probes.
    """
    return {"status": "ok"}


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
