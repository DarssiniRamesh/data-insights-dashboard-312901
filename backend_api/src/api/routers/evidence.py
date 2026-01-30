"""
PUBLIC_INTERFACE
Evidence router for evidence package retrieval and verification.
"""
from fastapi import APIRouter, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials

from database import get_connection
from schemas import EvidencePackageResponse, EvidenceArtifact, ErrorResponse
from services.evidence import EvidenceService, EvidenceError
from services.auth import AuthService, security
from utils import make_error_response, generate_id

router = APIRouter(
    prefix="/api/v1/evidence-packages",
    tags=["evidence"],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication failed"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)


@router.get(
    "/{evidence_package_id}",
    response_model=EvidencePackageResponse,
    summary="Get evidence package",
    description="Retrieve evidence package with integrity verification.",
    operation_id="get_evidence_package",
    responses={
        200: {"description": "Evidence package retrieved"},
        404: {"model": ErrorResponse, "description": "Evidence package not found"},
        409: {"model": ErrorResponse, "description": "Evidence integrity violation"},
    },
)
async def get_evidence_package(
    evidence_package_id: str,
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> EvidencePackageResponse:
    """
    PUBLIC_INTERFACE
    Get evidence package by ID with integrity verification.
    """
    db = get_connection()
    auth_service = AuthService(db)

    try:
        auth_service.get_current_user(credentials)

        evidence_service = EvidenceService(db)
        package = evidence_service.get_evidence_package(evidence_package_id)

        if not package:
            raise HTTPException(
                status_code=404,
                detail=make_error_response("NOT_FOUND", f"Evidence package {evidence_package_id} not found", generate_id("req")),
            )

        manifest = package.get("manifest", {})
        artifacts = [
            EvidenceArtifact(
                artifact_type=art["artifact_type"],
                artifact_id=art["artifact_id"],
                hash_sha256=art["hash_sha256"],
                storage_ref=art["storage_ref"],
            )
            for art in manifest.get("artifacts", [])
        ]

        return EvidencePackageResponse(
            evidence_package_id=package["evidence_package_id"],
            package_id=package["package_id"],
            package_version=package["package_version"],
            minted_identifier=package["minted_identifier"],
            artifacts=artifacts,
            created_at_utc=package["created_at_utc"],
        )

    except EvidenceError as e:
        if e.code == "EVIDENCE_INTEGRITY_VIOLATION":
            raise HTTPException(
                status_code=409,
                detail=make_error_response(e.code, e.message, generate_id("req"), e.details),
            )
        raise HTTPException(
            status_code=500,
            detail=make_error_response(e.code, e.message, generate_id("req"), e.details),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=make_error_response("INTERNAL_ERROR", f"Failed to get evidence package: {str(e)}", generate_id("req")),
        )
