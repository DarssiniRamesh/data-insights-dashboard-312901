"""
PUBLIC_INTERFACE
Validation router for validation report retrieval.
"""
from fastapi import APIRouter, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials

from src.database import get_connection
from src.schemas import ValidationReportSummary, ErrorResponse
from src.services.validation import ValidationService
from src.services.auth import AuthService, security
from src.utils import make_error_response, generate_id

router = APIRouter(
    prefix="/api/v1/validation-runs",
    tags=["validation"],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication failed"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)


@router.get(
    "/{validation_run_id}",
    response_model=ValidationReportSummary,
    summary="Get validation report",
    description="Retrieve validation report for a validation run.",
    operation_id="get_validation_report",
    responses={
        200: {"description": "Validation report retrieved"},
        404: {"model": ErrorResponse, "description": "Validation run not found"},
    }
)
async def get_validation_report(
    validation_run_id: str,
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> ValidationReportSummary:
    """
    PUBLIC_INTERFACE
    Get validation report by validation run ID.
    
    Authentication: Bearer token required
    
    Args:
        validation_run_id: Validation run identifier
        credentials: HTTP authorization credentials
        
    Returns:
        ValidationReportSummary with overall status, checks, and report hash
        
    Raises:
        HTTPException: 401 if auth fails, 404 if not found
    """
    db = get_connection()
    auth_service = AuthService(db)
    
    try:
        # Authenticate user
        user = auth_service.get_current_user(credentials)
        
        # Get validation report
        validation_service = ValidationService(db)
        report = validation_service.get_validation_report(validation_run_id)
        
        if not report:
            raise HTTPException(
                status_code=404,
                detail=make_error_response(
                    "NOT_FOUND",
                    f"Validation run {validation_run_id} not found",
                    generate_id("req")
                )
            )
        
        return ValidationReportSummary(
            validation_run_id=report["validation_run_id"],
            overall_status=report["overall_status"],
            checks=report["checks"],
            report_hash_sha256=report.get("report_hash_sha256", ""),
            created_at_utc=report["created_at_utc"]
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=make_error_response(
                "INTERNAL_ERROR",
                f"Failed to get validation report: {str(e)}",
                generate_id("req")
            )
        )
