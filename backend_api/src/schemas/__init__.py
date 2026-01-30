"""
Pydantic schemas for API request/response models.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


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
    schema_definition: Optional[SchemaDefinition] = None
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


class CreateSubmissionRequest(BaseModel):
    """Request to create a submission."""
    draft_id: str
    audit_context: AuditContext


class CreateSubmissionResponse(BaseModel):
    """Response from creating a submission."""
    submission_id: str
    package_id: str
    package_version: str
    state: str
    created_at_utc: str
    audit_event_id: str


class GetSubmissionResponse(BaseModel):
    """Response from getting a submission."""
    submission_id: str
    package_id: str
    package_version: str
    state: str
    latest_validation_run_id: Optional[str] = None
    active_deviation: bool = False
    created_at_utc: str
    last_updated_at_utc: str


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


class ApproveSubmissionRequest(BaseModel):
    """Request to approve a submission."""
    decision: Literal["publish", "reject"]
    required_preconditions: Optional[ApprovalPreconditions] = None
    signature: Optional[SignatureBlock] = None
    audit_context: AuditContext
    rationale: Optional[str] = None
    password: Optional[str] = Field(None, description="Password for electronic signature verification (required when using password reauthentication)")


class ApproveSubmissionResponse(BaseModel):
    """Response from approving a submission."""
    submission_id: str
    state: str
    published_version_id: Optional[str] = None
    published_at_utc: Optional[str] = None
    evidence_package_id: Optional[str] = None


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
