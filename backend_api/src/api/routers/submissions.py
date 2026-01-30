"""
PUBLIC_INTERFACE
Submissions router for data product submission and approval workflow.
"""
from fastapi import APIRouter, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials

from database import get_connection
from schemas import (
    CreateSubmissionRequest,
    CreateSubmissionResponse,
    GetSubmissionResponse,
    ApproveSubmissionRequest,
    ApproveSubmissionResponse,
    TriggerValidationRequest,
    TriggerValidationResponse,
    ErrorResponse,
)
from services.submission import SubmissionService
from services.validation import ValidationService
from services.approval import (
    ApprovalService,
    ApprovalError,
    AuthenticationError,
    AuthorizationError,
    SoDViolationError,
    SignatureError,
    InvalidStateError,
)
from services.auth import AuthService, security
from utils import make_error_response, generate_id

router = APIRouter(
    prefix="/api/v1/submissions",
    tags=["submissions"],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication failed"},
        403: {"model": ErrorResponse, "description": "Authorization failed"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)


@router.post(
    "",
    response_model=CreateSubmissionResponse,
    status_code=201,
    summary="Create a submission",
    description="Create a submission from a draft and trigger validation pipeline. Requires authentication.",
    operation_id="create_submission",
    responses={
        201: {"description": "Submission created and validation queued"},
        400: {"model": ErrorResponse, "description": "Invalid request or draft not found"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
    },
)
async def create_submission(
    request: CreateSubmissionRequest,
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> CreateSubmissionResponse:
    """
    PUBLIC_INTERFACE
    Create a submission from a draft.
    """
    db = get_connection()
    auth_service = AuthService(db)

    try:
        user = auth_service.get_current_user(credentials)

        if request.audit_context.actor_user_id != user["user_id"]:
            raise HTTPException(
                status_code=403,
                detail=make_error_response(
                    "AUTHORIZATION_FAILED",
                    "audit_context.actor_user_id must match authenticated user",
                    request.audit_context.client_request_id,
                    {"expected": user["user_id"], "provided": request.audit_context.actor_user_id},
                ),
            )

        if request.audit_context.actor_role != user["role"]:
            raise HTTPException(
                status_code=403,
                detail=make_error_response(
                    "AUTHORIZATION_FAILED",
                    "audit_context.actor_role must match authenticated user role",
                    request.audit_context.client_request_id,
                    {"expected": user["role"], "provided": request.audit_context.actor_role},
                ),
            )

        submission_service = SubmissionService(db)
        result = submission_service.create_submission(
            draft_id=request.draft_id,
            actor_user_id=user["user_id"],
            actor_role=user["role"],
            correlation_id=request.audit_context.client_request_id,
        )

        return CreateSubmissionResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=make_error_response("INVALID_REQUEST", str(e), request.audit_context.client_request_id),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=make_error_response(
                "INTERNAL_ERROR",
                f"Failed to create submission: {str(e)}",
                request.audit_context.client_request_id,
            ),
        )


@router.get(
    "/{submission_id}",
    response_model=GetSubmissionResponse,
    summary="Get submission",
    description="Retrieve submission details including current state and validation status.",
    operation_id="get_submission",
    responses={
        200: {"description": "Submission details retrieved"},
        404: {"model": ErrorResponse, "description": "Submission not found"},
    },
)
async def get_submission(
    submission_id: str,
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> GetSubmissionResponse:
    """
    PUBLIC_INTERFACE
    Get submission by ID.
    """
    db = get_connection()
    auth_service = AuthService(db)

    try:
        auth_service.get_current_user(credentials)

        submission_service = SubmissionService(db)
        submission = submission_service.get_submission(submission_id)

        if not submission:
            raise HTTPException(
                status_code=404,
                detail=make_error_response("NOT_FOUND", f"Submission {submission_id} not found", generate_id("req")),
            )

        validation_service = ValidationService(db)
        validation_runs = validation_service.list_validation_runs(submission_id)
        latest_validation_run_id = validation_runs[0]["validation_run_id"] if validation_runs else None

        return GetSubmissionResponse(
            submission_id=submission["submission_id"],
            package_id=submission["package_id"],
            package_version=submission["package_version"],
            state=submission["state"],
            latest_validation_run_id=latest_validation_run_id,
            active_deviation=bool(submission.get("active_deviation_id")),
            created_at_utc=submission["created_at_utc"],
            last_updated_at_utc=submission["last_updated_at_utc"],
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=make_error_response("INTERNAL_ERROR", f"Failed to get submission: {str(e)}", generate_id("req")),
        )


@router.post(
    "/{submission_id}/validate",
    response_model=TriggerValidationResponse,
    summary="Trigger validation",
    description="Trigger validation run for a submission. Creates validation job and executes quality gates.",
    operation_id="trigger_validation",
    responses={
        200: {"description": "Validation triggered successfully"},
        400: {"model": ErrorResponse, "description": "Invalid submission state"},
        404: {"model": ErrorResponse, "description": "Submission not found"},
    },
)
async def trigger_validation(
    submission_id: str,
    request: TriggerValidationRequest,
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> TriggerValidationResponse:
    """
    PUBLIC_INTERFACE
    Trigger validation run for a submission.
    """
    db = get_connection()
    auth_service = AuthService(db)

    try:
        user = auth_service.get_current_user(credentials)

        if request.audit_context.actor_user_id != user["user_id"]:
            raise HTTPException(
                status_code=403,
                detail=make_error_response(
                    "AUTHORIZATION_FAILED",
                    "audit_context.actor_user_id must match authenticated user",
                    request.audit_context.client_request_id,
                ),
            )

        validation_service = ValidationService(db)
        validation_service.run_validation(
            submission_id=submission_id,
            validation_profile=request.validation_profile,
            actor_user_id=user["user_id"],
            actor_role=user["role"],
            correlation_id=request.audit_context.client_request_id,
        )

        return TriggerValidationResponse(
            pipeline_job_id=generate_id("job"),
            state="succeeded",
            audit_event_id=generate_id("audit"),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=make_error_response("INVALID_REQUEST", str(e), request.audit_context.client_request_id),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=make_error_response(
                "INTERNAL_ERROR",
                f"Failed to trigger validation: {str(e)}",
                request.audit_context.client_request_id,
            ),
        )


@router.post(
    "/{submission_id}/approve",
    response_model=ApproveSubmissionResponse,
    summary="Approve or reject submission",
    description="Approve or reject a submission with electronic signature and SoD validation. Creates evidence package on approval.",
    operation_id="approve_submission",
    responses={
        200: {"description": "Submission approved or rejected"},
        400: {"model": ErrorResponse, "description": "Invalid request or preconditions not met"},
        403: {"model": ErrorResponse, "description": "Authorization failed or SoD violation"},
        404: {"model": ErrorResponse, "description": "Submission not found"},
        409: {"model": ErrorResponse, "description": "Invalid state or validation failed"},
    },
)
async def approve_submission(
    submission_id: str,
    request: ApproveSubmissionRequest,
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> ApproveSubmissionResponse:
    """
    PUBLIC_INTERFACE
    Approve or reject a submission.
    """
    db = get_connection()
    auth_service = AuthService(db)

    try:
        user = auth_service.get_current_user(credentials)

        if request.audit_context.actor_user_id != user["user_id"]:
            raise HTTPException(
                status_code=403,
                detail=make_error_response(
                    "AUTHORIZATION_FAILED",
                    "audit_context.actor_user_id must match authenticated user",
                    request.audit_context.client_request_id,
                ),
            )

        if request.audit_context.actor_role != user["role"]:
            raise HTTPException(
                status_code=403,
                detail=make_error_response(
                    "AUTHORIZATION_FAILED",
                    "audit_context.actor_role must match authenticated user role",
                    request.audit_context.client_request_id,
                    {"expected": user["role"], "provided": request.audit_context.actor_role},
                ),
            )

        approval_service = ApprovalService(db)
        result = approval_service.approve_submission(
            submission_id=submission_id,
            decision=request.decision,
            approver_user_id=user["user_id"],
            approver_role=user["role"],
            signature=request.signature.dict() if request.signature else None,
            correlation_id=request.audit_context.client_request_id,
            required_preconditions=request.required_preconditions.dict() if request.required_preconditions else None,
            rationale=request.rationale,
            password_for_esign=request.password,
        )

        return ApproveSubmissionResponse(
            submission_id=result["submission_id"],
            state=result["state"],
            published_version_id=result.get("published_version_id"),
            published_at_utc=result.get("published_at_utc"),
            evidence_package_id=result.get("evidence_package_id"),
        )

    except AuthenticationError as e:
        raise HTTPException(
            status_code=401,
            detail=make_error_response(e.code, e.message, request.audit_context.client_request_id, e.details),
        )
    except AuthorizationError as e:
        raise HTTPException(
            status_code=403,
            detail=make_error_response(e.code, e.message, request.audit_context.client_request_id, e.details),
        )
    except SoDViolationError as e:
        raise HTTPException(
            status_code=409,
            detail=make_error_response(e.code, e.message, request.audit_context.client_request_id, e.details),
        )
    except SignatureError as e:
        raise HTTPException(
            status_code=409,
            detail=make_error_response(e.code, e.message, request.audit_context.client_request_id, e.details),
        )
    except InvalidStateError as e:
        raise HTTPException(
            status_code=409,
            detail=make_error_response(e.code, e.message, request.audit_context.client_request_id, e.details),
        )
    except ApprovalError as e:
        raise HTTPException(
            status_code=400,
            detail=make_error_response(e.code, e.message, request.audit_context.client_request_id, e.details),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=make_error_response(
                "INTERNAL_ERROR",
                f"Failed to approve submission: {str(e)}",
                request.audit_context.client_request_id,
            ),
        )
