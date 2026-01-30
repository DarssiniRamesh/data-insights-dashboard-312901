"""
PUBLIC_INTERFACE
Drafts router for data product draft management.
"""
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials
from typing import Dict, Any

from src.database import get_connection
from src.schemas import CreateDraftRequest, CreateDraftResponse, ErrorResponse
from src.services.draft import DraftService
from src.services.auth import AuthService, security
from src.utils import make_error_response

router = APIRouter(
    prefix="/api/v1/drafts",
    tags=["drafts"],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication failed"},
        403: {"model": ErrorResponse, "description": "Authorization failed"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)


@router.post(
    "",
    response_model=CreateDraftResponse,
    status_code=201,
    summary="Create a draft",
    description="Create a new data product draft with audit logging. Requires authentication.",
    operation_id="create_draft",
    responses={
        201: {"description": "Draft created successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request payload"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
    }
)
async def create_draft(
    request: CreateDraftRequest,
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> CreateDraftResponse:
    """
    PUBLIC_INTERFACE
    Create a new data product draft.
    
    This endpoint allows publishers to create a draft data product package that can
    later be submitted for validation and approval.
    
    Authentication: Bearer token required
    Authorization: publisher, steward, governance_admin roles
    
    Args:
        request: Draft creation request with package definition and audit context
        credentials: HTTP authorization credentials
        
    Returns:
        CreateDraftResponse with draft_id, package_id, version, state, and audit_event_id
        
    Raises:
        HTTPException: 401 if authentication fails, 400 if validation fails, 500 on error
    """
    db = get_connection()
    auth_service = AuthService(db)
    
    try:
        # Authenticate user
        user = auth_service.get_current_user(credentials)
        
        # Validate actor matches authenticated user
        if request.audit_context.actor_user_id != user["user_id"]:
            raise HTTPException(
                status_code=403,
                detail=make_error_response(
                    "AUTHORIZATION_FAILED",
                    "audit_context.actor_user_id must match authenticated user",
                    request.audit_context.client_request_id,
                    {"expected": user["user_id"], "provided": request.audit_context.actor_user_id}
                )
            )
        
        if request.audit_context.actor_role != user["role"]:
            raise HTTPException(
                status_code=403,
                detail=make_error_response(
                    "AUTHORIZATION_FAILED",
                    "audit_context.actor_role must match authenticated user role",
                    request.audit_context.client_request_id,
                    {"expected": user["role"], "provided": request.audit_context.actor_role}
                )
            )
        
        # Create draft
        draft_service = DraftService(db)
        result = draft_service.create_draft(
            package=request.package.dict(),
            actor_user_id=user["user_id"],
            actor_role=user["role"],
            correlation_id=request.audit_context.client_request_id
        )
        
        return CreateDraftResponse(**result)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=make_error_response(
                "INTERNAL_ERROR",
                f"Failed to create draft: {str(e)}",
                request.audit_context.client_request_id
            )
        )
