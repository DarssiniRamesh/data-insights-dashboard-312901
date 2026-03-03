"""
PUBLIC_INTERFACE
Submissions router - backward compatibility wrapper for data assets.

FR/NFR implementation summary (GxP traceability):
- FR-DPP-001: POST /api/v1/submissions (deprecated) maps to data-asset creation behavior.
- FR-DPP-002: GET /api/v1/submissions/{submission_id} (deprecated) maps to data-asset retrieval behavior.
- NFR-DPP-009/NFR-DPP-010 (Identity/AuthZ): Endpoints require authentication via get_current_user dependency.
- NFR-DPP-020 (Automation support): Maintains legacy contract behavior for existing tests/clients.

DEPRECATED: This router provides backward compatibility for existing clients.
New clients should use /api/v1/data-assets endpoints instead.

All 'submission' terminology is deprecated in favor of 'data asset' (deprecated, use data asset).
"""
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from ...database import get_connection
from services.data_asset import DataAssetService
from services.validation import ValidationService
from services.approval import ApprovalService, SoDViolationException, SignatureVerificationException
from services.auth import get_current_user
from schemas import (
    CreateSubmissionResponse,
    GetSubmissionResponse,
    TriggerValidationRequest,
    TriggerValidationResponse,
    ApproveSubmissionRequest,
    ApproveSubmissionResponse,
    ErrorResponse,
)

router = APIRouter(prefix="/api/v1/submissions", tags=["submissions"])


def add_deprecation_header(response: JSONResponse) -> JSONResponse:
    """Add deprecation warning header to response."""
    response.headers["X-API-Deprecated"] = "true"
    response.headers["X-API-Deprecation-Message"] = "Use /api/v1/data-assets endpoints instead"
    return response


# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=CreateSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a submission",
    description="Create a submission from a draft and trigger validation pipeline. Requires authentication. DEPRECATED: Use /api/v1/data-assets instead.",
    operation_id="create_submission",
    responses={
        201: {"description": "Submission created and validation queued"},
        400: {"description": "Invalid request or draft not found", "model": ErrorResponse},
        401: {"description": "Authentication required", "model": ErrorResponse},
        403: {"description": "Authorization failed", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    deprecated=True,
)
# FR-DPP-001 (REQ): Create a data asset (legacy submission API) — this endpoint maps to the data-asset
# creation flow and returns an identifier used for subsequent workflow steps.
def create_submission(
    payload: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    PUBLIC_INTERFACE
    Create a submission (deprecated - maps to data asset creation).
    """
    try:
        conn = get_connection()
        service = DataAssetService(conn)

        # Extract draft_id from payload (flexible format)
        draft_id = payload.get("draft_id")
        if not draft_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="draft_id is required")

        # Use default metadata for backward compatibility
        result = service.create_submission(
            draft_id=draft_id,
            actor_user_id=current_user["user_id"],
            actor_role=current_user.get("primary_role", "publisher"),
            correlation_id=payload.get("audit_context", {}).get("client_request_id", "legacy"),
        )

        response = JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=result,
        )
        return add_deprecation_header(response)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# PUBLIC_INTERFACE
@router.get(
    "/{submission_id}",
    response_model=GetSubmissionResponse,
    summary="Get submission",
    description="Retrieve submission details including current state and validation status. DEPRECATED: Use /api/v1/data-assets/{id} instead.",
    operation_id="get_submission",
    responses={
        200: {"description": "Submission details retrieved"},
        401: {"description": "Authentication failed", "model": ErrorResponse},
        403: {"description": "Authorization failed", "model": ErrorResponse},
        404: {"description": "Submission not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    deprecated=True,
)
# FR-DPP-002 (REQ): Retrieve a data asset (legacy submission API) — returns current state and key fields
# for dashboard display and traceable workflow actions.
def get_submission(
    submission_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    PUBLIC_INTERFACE
    Get a submission by ID (maps to data asset).
    """
    try:
        conn = get_connection()
        service = DataAssetService(conn)
        validation_service = ValidationService(conn)

        data_asset = service.get_data_asset(submission_id)
        if not data_asset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

        # Get latest validation run if any
        latest_validation = validation_service.get_latest_validation_for_data_asset(submission_id)

        # Defensive access: some older DB rows (or partial test fixtures) may not include
        # the timestamp fields; raising KeyError here causes a 500 and breaks the dashboard.
        response_data = {
            "submission_id": data_asset.get("data_asset_id"),
            "package_id": data_asset.get("package_id"),
            "package_version": data_asset.get("package_version"),
            "state": data_asset.get("state"),
            "latest_validation_run_id": latest_validation.get("validation_run_id") if latest_validation else None,
            "active_deviation": bool(data_asset.get("active_deviation_id")),
            "created_at_utc": data_asset.get("created_at_utc") or data_asset.get("created_at"),
            "last_updated_at_utc": data_asset.get("last_updated_at_utc") or data_asset.get("updated_at_utc"),
        }

        response = JSONResponse(content=response_data)
        return add_deprecation_header(response)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# PUBLIC_INTERFACE
@router.post(
    "/{submission_id}/validate",
    response_model=TriggerValidationResponse,
    summary="Trigger validation",
    description="Trigger validation run for a submission. Creates validation job and executes quality gates. DEPRECATED: Use /api/v1/data-assets/{id}/validate instead.",
    operation_id="trigger_validation",
    responses={
        200: {"description": "Validation triggered successfully"},
        400: {"description": "Invalid submission state", "model": ErrorResponse},
        401: {"description": "Authentication failed", "model": ErrorResponse},
        403: {"description": "Authorization failed", "model": ErrorResponse},
        404: {"description": "Submission not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    deprecated=True,
)
def trigger_validation(
    submission_id: str,
    request: TriggerValidationRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    PUBLIC_INTERFACE
    Trigger validation for a submission (maps to data asset).
    """
    try:
        conn = get_connection()
        validation_service = ValidationService(conn)

        result = validation_service.execute_validation_run(
            data_asset_id=submission_id,
            profile=request.validation_profile,
            actor_user_id=current_user["user_id"],
            actor_role=current_user.get("primary_role", "publisher"),
            correlation_id=request.audit_context.client_request_id,
        )

        response_data = {
            "pipeline_job_id": result["validation_run_id"],
            "state": "completed",
            "audit_event_id": result["validation_run_id"],
        }

        response = JSONResponse(content=response_data)
        return add_deprecation_header(response)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# PUBLIC_INTERFACE
@router.post(
    "/{submission_id}/approve",
    response_model=ApproveSubmissionResponse,
    summary="Approve or reject submission",
    description="Approve or reject a submission with electronic signature and SoD validation. Creates evidence package on approval. DEPRECATED: Use /api/v1/data-assets/{id}/approve instead.",
    operation_id="approve_submission",
    responses={
        200: {"description": "Submission approved or rejected"},
        400: {"description": "Invalid request or preconditions not met", "model": ErrorResponse},
        401: {"description": "Authentication failed", "model": ErrorResponse},
        403: {"description": "Authorization failed or SoD violation", "model": ErrorResponse},
        404: {"description": "Submission not found", "model": ErrorResponse},
        409: {"description": "Invalid state or validation failed", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    deprecated=True,
)
def approve_submission(
    submission_id: str,
    request: ApproveSubmissionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    PUBLIC_INTERFACE
    Approve or reject a submission (maps to data asset).
    """
    try:
        conn = get_connection()
        approval_service = ApprovalService(conn)

        result = approval_service.process_approval(
            data_asset_id=submission_id,
            decision=request.decision,
            signature=request.signature.model_dump() if request.signature else None,
            password=request.password,
            rationale=request.rationale,
            actor_user_id=current_user["user_id"],
            actor_role=current_user.get("primary_role", "steward"),
            correlation_id=request.audit_context.client_request_id,
            required_preconditions=request.required_preconditions.model_dump() if request.required_preconditions else None,
        )

        response_data = {
            "submission_id": result["data_asset_id"],
            "state": result["state"],
            "published_version_id": result.get("published_version_id"),
            "published_at_utc": result.get("published_at_utc"),
            "evidence_package_id": result.get("evidence_package_id"),
        }

        response = JSONResponse(content=response_data)
        return add_deprecation_header(response)

    except SoDViolationException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except SignatureVerificationException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
