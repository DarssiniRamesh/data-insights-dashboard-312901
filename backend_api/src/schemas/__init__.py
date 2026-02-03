"""
Pydantic schemas for API request/response models.

Standard terminology: 'data asset' with metadata constrained to title, description, owner.
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict


class AuditContext(BaseModel):
    """Audit context for attributable actions."""
    actor_user_id: str
    actor_role: Literal["publisher", "steward", "governance_admin", "auditor", "system"]
    timestamp_utc: str
    client_request_id: str


class SignatureBlock(BaseModel):
    """Electronic signature evidence."""
    signer_user_id: str
    signer_role: Literal["steward", "governance_admin", "quality_owner"]
    signed_at_utc: str
    reauthentication_method: Literal["password", "mfa", "sso_reauth"]
    signature_reason: str
    signature_hash: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: Dict[str, Any]


# Data Asset Metadata Models (standardized to title, description, owner)
class DataAssetMetadata(BaseModel):
    """
    Data asset metadata with standardized fields.
    
    Fields:
    - title: Required, 1-200 characters
    - description: Optional, max 2000 characters
    - owner: Required, 1-120 characters (email, username, or identifier)
    """
    model_config = ConfigDict(extra='forbid')
    
    title: str = Field(..., min_length=1, max_length=200, description="Data asset title (required, 1-200 chars)")
    description: Optional[str] = Field(None, max_length=2000, description="Data asset description (optional, max 2000 chars)")
    owner: str = Field(..., min_length=1, max_length=120, description="Data asset owner identifier (required, 1-120 chars)")

    @field_validator('title', 'owner')
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        """Ensure title and owner are not just whitespace."""
        if not v or not v.strip():
            raise ValueError("Field must not be empty or whitespace only")
        return v.strip()

    @field_validator('description')
    @classmethod
    def validate_description(cls, v: Optional[str]) -> Optional[str]:
        """Trim description if provided."""
        if v is not None:
            return v.strip() if v.strip() else None
        return v


class DataAssetCreate(BaseModel):
    """Request to create a data asset with standardized metadata."""
    model_config = ConfigDict(extra='forbid')
    
    metadata: DataAssetMetadata = Field(..., description="Data asset metadata (title, description, owner)")
    audit_context: AuditContext


class DataAssetUpdate(BaseModel):
    """Request to update data asset metadata."""
    model_config = ConfigDict(extra='forbid')
    
    metadata: DataAssetMetadata = Field(..., description="Updated data asset metadata")
    audit_context: AuditContext


# Legacy models for backward compatibility
class DatasetReference(BaseModel):
    """Dataset reference in package."""
    format: str
    storage_ref: str
    hash_sha256: str
    row_count: Optional[int] = None
    contains_phi: Optional[bool] = False


class SchemaField(BaseModel):
    """Schema field definition."""
    name: str
    data_type: str
    nullable: bool
    critical: bool = False


class SchemaDefinition(BaseModel):
    """Schema definition."""
    schema_id: str
    schema_version: str
    fields: List[SchemaField]


class ProductMetadata(BaseModel):
    """Product metadata."""
    name: str
    domain: str
    owner_group: str
    steward_user_id: str
    version_intent: str = "minor"


class ControlsMetadata(BaseModel):
    """Controls and retention metadata."""
    classification: str
    retention: Optional[Dict[str, Any]] = None


class DataProductPackage(BaseModel):
    """Data product package definition."""
    product: ProductMetadata
    dataset: DatasetReference
    schema: Optional[SchemaDefinition] = None
    controls: ControlsMetadata
    sop_references: List[str] = []


class CreateDraftRequest(BaseModel):
    """Request to create a draft."""
    package: DataProductPackage
    audit_context: AuditContext


class CreateDraftResponse(BaseModel):
    """Response from creating a draft."""
    draft_id: str
    package_id: str
    package_version: str
    state: str
    created_at_utc: str
    audit_event_id: str


class CreateDataAssetRequest(BaseModel):
    """Request to create a data asset."""
    draft_id: str
    metadata: DataAssetMetadata = Field(..., description="Data asset metadata (title, description, owner)")
    audit_context: AuditContext


class CreateDataAssetResponse(BaseModel):
    """Response from creating a data asset."""
    data_asset_id: str
    package_id: str
    package_version: str
    title: str
    description: Optional[str]
    owner: str
    state: str
    created_at_utc: str
    audit_event_id: str


class GetDataAssetResponse(BaseModel):
    """Response from getting a data asset."""
    data_asset_id: str
    package_id: str
    package_version: str
    title: str
    description: Optional[str]
    owner: str
    state: str
    latest_validation_run_id: Optional[str] = None
    active_deviation: bool = False
    created_at_utc: str
    last_updated_at_utc: str


# Backward compatibility aliases (deprecated)
CreateSubmissionRequest = CreateDataAssetRequest
CreateSubmissionResponse = CreateDataAssetResponse
GetSubmissionResponse = GetDataAssetResponse


class ValidationCheck(BaseModel):
    """Validation check result."""
    check_name: str
    status: Literal["pass", "fail"]
    metrics: Dict[str, Any] = {}
    findings: List[Dict[str, Any]] = []


class ValidationReportSummary(BaseModel):
    """Validation report summary."""
    validation_run_id: str
    overall_status: Literal["pass", "fail"]
    checks: List[ValidationCheck]
    report_hash_sha256: str
    created_at_utc: str


class ApprovalPreconditions(BaseModel):
    """Required preconditions for approval."""
    latest_validation_run_id: str


class ApproveDataAssetRequest(BaseModel):
    """Request to approve a data asset."""
    decision: Literal["publish", "reject"]
    required_preconditions: Optional[ApprovalPreconditions] = None
    signature: Optional[SignatureBlock] = None
    audit_context: AuditContext
    rationale: Optional[str] = None
    password: Optional[str] = Field(None, description="Password for electronic signature verification (required when using password reauthentication)")


class ApproveDataAssetResponse(BaseModel):
    """Response from approving a data asset."""
    data_asset_id: str
    state: str
    published_version_id: Optional[str] = None
    published_at_utc: Optional[str] = None
    evidence_package_id: Optional[str] = None


# Backward compatibility aliases (deprecated)
ApproveSubmissionRequest = ApproveDataAssetRequest
ApproveSubmissionResponse = ApproveDataAssetResponse


class TriggerValidationRequest(BaseModel):
    """Request to trigger validation."""
    validation_profile: str = "baseline"
    audit_context: AuditContext


class TriggerValidationResponse(BaseModel):
    """Response from triggering validation."""
    pipeline_job_id: str
    state: str
    audit_event_id: str


class AuditEvent(BaseModel):
    """Audit event."""
    audit_event_id: str
    event_type: str
    entity_type: str
    entity_id: str
    actor_user_id: str
    actor_role: str
    timestamp_utc: str
    correlation_id: str
    result: Literal["success", "failure", "blocked"]
    details_json: Optional[str] = None


class GetAuditEventsResponse(BaseModel):
    """Response from querying audit events."""
    events: List[AuditEvent]


class EvidenceArtifact(BaseModel):
    """Evidence artifact reference."""
    artifact_type: str
    artifact_id: str
    hash_sha256: str
    storage_ref: str


class EvidencePackageResponse(BaseModel):
    """Evidence package response."""
    evidence_package_id: str
    package_id: str
    package_version: str
    minted_identifier: str
    artifacts: List[EvidenceArtifact]
    created_at_utc: str
