"""
PUBLIC_INTERFACE
Audit router for audit event queries.
"""
from fastapi import APIRouter, HTTPException, Security, Query
from fastapi.security import HTTPAuthorizationCredentials
from typing import Optional

from src.database import get_connection
from src.schemas import GetAuditEventsResponse, AuditEvent, ErrorResponse
from src.services.audit import AuditService
from src.services.auth import AuthService, security, require_roles
from src.utils import make_error_response, generate_id

router = APIRouter(
    prefix="/api/v1/audit",
    tags=["audit"],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication failed"},
        403: {"model": ErrorResponse, "description": "Authorization failed"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)


@router.get(
    "/events",
    response_model=GetAuditEventsResponse,
    summary="Query audit events",
    description="Query audit events with optional filters. Restricted to auditor and governance_admin roles.",
    operation_id="query_audit_events",
    responses={
        200: {"description": "Audit events retrieved"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
    }
)
async def query_audit_events(
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum events to return"),
    current_user: dict = Security(require_roles(["auditor", "admin", "governance_admin"]))
) -> GetAuditEventsResponse:
    """
    PUBLIC_INTERFACE
    Query audit events.
    
    This endpoint is restricted to auditor and governance_admin roles for compliance.
    
    Authentication: Bearer token required
    Authorization: auditor, governance_admin roles only
    
    Args:
        entity_type: Optional filter by entity type
        entity_id: Optional filter by entity ID
        limit: Maximum number of events to return (1-1000)
        credentials: HTTP authorization credentials
        
    Returns:
        GetAuditEventsResponse with list of audit events
        
    Raises:
        HTTPException: 401 if auth fails, 403 if insufficient permissions
    """
    db = get_connection()
    auth_service = AuthService(db)
    
    try:
        # Authenticate user
        user = auth_service.get_current_user(credentials)
        
        # Check authorization - only auditor and governance_admin can query audit events
        if user["role"] not in ["auditor", "governance_admin"]:
            raise HTTPException(
                status_code=403,
                detail=make_error_response(
                    "AUTHORIZATION_FAILED",
                    f"Role '{user['role']}' not authorized to query audit events",
                    generate_id("req"),
                    {"required_roles": ["auditor", "governance_admin"], "user_role": user["role"]}
                )
            )
        
        # Query audit events
        audit_service = AuditService(db)
        events = audit_service.query_events(
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit
        )
        
        # Convert to response model
        audit_events = [
            AuditEvent(
                audit_event_id=event["audit_event_id"],
                event_type=event["event_type"],
                entity_type=event["entity_type"],
                entity_id=event["entity_id"],
                actor_user_id=event["actor_user_id"],
                actor_role=event["actor_role"],
                timestamp_utc=event["timestamp_utc"],
                correlation_id=event["correlation_id"],
                result=event["result"],
                details_json=event.get("details_json")
            )
            for event in events
        ]
        
        return GetAuditEventsResponse(events=audit_events)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=make_error_response(
                "INTERNAL_ERROR",
                f"Failed to query audit events: {str(e)}",
                generate_id("req")
            )
        )
