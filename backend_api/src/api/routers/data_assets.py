"""
PUBLIC_INTERFACE
Data assets router for managing data asset lifecycle.

FR/NFR implementation summary (GxP traceability):
- FR-DPP-001: POST /api/v1/data-assets creates a data asset with standardized metadata.
- FR-DPP-002: GET /api/v1/data-assets/{data_asset_id} retrieves a data asset for UI/workflow visibility.
- NFR-DPP-009/NFR-DPP-010 (Identity/AuthZ): Endpoints require authentication via get_current_user dependency.
- NFR-DPP-002 (Auditability): Endpoints accept audit_context and propagate correlation IDs for audit linking.

Terminology: 'data asset' with standardized metadata (title, description, owner)
"""
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from database import get_connection
from services.data_asset import DataAssetService
from services.validation import ValidationService
from services.approval import ApprovalService, SoDViolationException, SignatureVerificationException
from services.auth import AuthService, get_current_user
from schemas import (
    CreateDataAssetRequest,
    CreateDataAssetResponse,
    GetDataAssetResponse,
    TriggerValidationRequest,
    TriggerValidationResponse,
    ApproveDataAssetRequest,
    ApproveDataAssetResponse,
    ErrorResponse,
)

router = APIRouter(prefix="/api/v1/data-assets", tags=["data-assets"])


# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=CreateDataAssetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a data asset",
    description="Create a data asset from a draft with standardized metadata (title, description, owner) and trigger validation pipeline. Requires authentication.",
    operation_id="create_data_asset",
    responses={
        201: {"description": "Data asset created and validation queued"},
        400: {"description": "Invalid request or draft not found", "model": ErrorResponse},
        401: {"description": "Authentication required", "model": ErrorResponse},
        403: {"description": "Authorization failed", "model": ErrorResponse},
        422: {"description": "Validation error - metadata constraints not met", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
# FR-DPP-001 (REQ): Create a data asset via API using a draft_id plus standardized metadata
# (title/description/owner). Enforces metadata constraints and links to an audit_context (client_request_id).
def create_data_asset(
    request: CreateDataAssetRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    PUBLIC_INTERFACE
    Create a data asset with standardized metadata.
    
    Metadata constraints:
    - title: Required, 1-200 characters
    - description: Optional, max 2000 characters
    - owner: Required, 1-120 characters
    
    Extra fields in metadata are rejected (422 error).
    """
    try:
        conn = get_connection()
        service = DataAssetService(conn)

        result = service.create_data_asset(
            draft_id=request.draft_id,
            title=request.metadata.title,
            description=request.metadata.description,
            owner=request.metadata.owner,
            actor_user_id=current_user["user_id"],
            actor_role=current_user.get("primary_role", "publisher"),
            correlation_id=request.audit_context.client_request_id,
        )

        return CreateDataAssetResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# PUBLIC_INTERFACE
@router.get(
    "/{data_asset_id}",
    response_model=GetDataAssetResponse,
    summary="Get data asset",
    description="Retrieve data asset details including current state and validation status.",
    operation_id="get_data_asset",
    responses={
        200: {"description": "Data asset details retrieved"},
        401: {"description": "Authentication failed", "model": ErrorResponse},
        403: {"description": "Authorization failed", "model": ErrorResponse},
        404: {"description": "Data asset not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
# FR-DPP-002 (REQ): Retrieve a data asset (by ID) including standardized metadata and current workflow state,
# for dashboard display and downstream validation/approval decisions.
def get_data_asset(
    data_asset_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    PUBLIC_INTERFACE
    Get a data asset by ID.
    """
    try:
        conn = get_connection()
        service = DataAssetService(conn)
        validation_service = ValidationService(conn)

        data_asset = service.get_data_asset(data_asset_id)
        if not data_asset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data asset not found")

        # Get latest validation run if any
        latest_validation = validation_service.get_latest_validation_for_data_asset(data_asset_id)

        return GetDataAssetResponse(
            data_asset_id=data_asset["data_asset_id"],
            package_id=data_asset["package_id"],
            package_version=data_asset["package_version"],
            title=data_asset["title"],
            description=data_asset.get("description"),
            owner=data_asset["owner"],
            state=data_asset["state"],
            latest_validation_run_id=latest_validation.get("validation_run_id") if latest_validation else None,
            active_deviation=bool(data_asset.get("active_deviation_id")),
            created_at_utc=data_asset["created_at_utc"],
            last_updated_at_utc=data_asset["last_updated_at_utc"],
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# PUBLIC_INTERFACE
@router.post(
    "/{data_asset_id}/validate",
    response_model=TriggerValidationResponse,
    summary="Trigger validation",
    description="Trigger validation run for a data asset. Creates validation job and executes quality gates.",
    operation_id="trigger_data_asset_validation",
    responses={
        200: {"description": "Validation triggered successfully"},
        400: {"description": "Invalid data asset state", "model": ErrorResponse},
        401: {"description": "Authentication failed", "model": ErrorResponse},
        403: {"description": "Authorization failed", "model": ErrorResponse},
        404: {"description": "Data asset not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
def trigger_validation(
    data_asset_id: str,
    request: TriggerValidationRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    PUBLIC_INTERFACE
    Trigger validation for a data asset.
    """
    try:
        conn = get_connection()
        validation_service = ValidationService(conn)

        result = validation_service.execute_validation_run(
            data_asset_id=data_asset_id,
            profile=request.validation_profile,
            actor_user_id=current_user["user_id"],
            actor_role=current_user.get("primary_role", "publisher"),
            correlation_id=request.audit_context.client_request_id,
        )

        return TriggerValidationResponse(
            pipeline_job_id=result["validation_run_id"],
            state="completed",
            audit_event_id=result["validation_run_id"],
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# PUBLIC_INTERFACE
@router.post(
    "/{data_asset_id}/approve",
    response_model=ApproveDataAssetResponse,
    summary="Approve or reject data asset",
    description="Approve or reject a data asset with electronic signature and SoD validation. Creates evidence package on approval.",
    operation_id="approve_data_asset",
    responses={
        200: {"description": "Data asset approved or rejected"},
        400: {"description": "Invalid request or preconditions not met", "model": ErrorResponse},
        401: {"description": "Authentication failed", "model": ErrorResponse},
        403: {"description": "Authorization failed or SoD violation", "model": ErrorResponse},
        404: {"description": "Data asset not found", "model": ErrorResponse},
        409: {"description": "Invalid state or validation failed", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
def approve_data_asset(
    data_asset_id: str,
    request: ApproveDataAssetRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    PUBLIC_INTERFACE
    Approve or reject a data asset with e-signature and SoD enforcement.
    """
    try:
        conn = get_connection()
        approval_service = ApprovalService(conn)

        result = approval_service.process_approval(
            data_asset_id=data_asset_id,
            decision=request.decision,
            signature=request.signature.model_dump() if request.signature else None,
            password=request.password,
            rationale=request.rationale,
            actor_user_id=current_user["user_id"],
            actor_role=current_user.get("primary_role", "steward"),
            correlation_id=request.audit_context.client_request_id,
            required_preconditions=request.required_preconditions.model_dump() if request.required_preconditions else None,
        )

        return ApproveDataAssetResponse(**result)

    except SoDViolationException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except SignatureVerificationException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
