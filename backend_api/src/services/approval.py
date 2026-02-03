"""
PUBLIC_INTERFACE
Approval service for managing data asset approvals with electronic signatures.

FR-APP-001: Electronic signature support (21 CFR Part 11 aligned)
FR-APP-002: Segregation of Duties (SoD) enforcement
FR-APP-003: Evidence package generation on approval
"""
from typing import Dict, Any, Optional
import json
import hashlib

from utils import generate_id, utc_now_iso
from services.audit import AuditService
from services.validation import ValidationService
from services.evidence import EvidenceService


class ApprovalException(Exception):
    """Base exception for approval-related errors."""
    pass


class SoDViolationException(ApprovalException):
    """Exception raised when Segregation of Duties is violated."""
    pass


class SignatureVerificationException(ApprovalException):
    """Exception raised when electronic signature verification fails."""
    pass


class ApprovalService:
    """
    Service for managing data asset approval workflow.
    
    Implements electronic signature validation, SoD enforcement, and evidence package management.
    """

    def __init__(self, db_connection):
        self.db = db_connection
        self.audit_service = AuditService(db_connection)
        self.validation_service = ValidationService(db_connection)
        self.evidence_service = EvidenceService(db_connection)

    # PUBLIC_INTERFACE
    def verify_electronic_signature(
        self,
        signature: Dict[str, Any],
        password: Optional[str],
        actor_user_id: str,
    ) -> bool:
        """
        PUBLIC_INTERFACE
        Verify an electronic signature block.

        FR-APP-001: Implements e-signature verification aligned with 21 CFR Part 11.

        Args:
            signature: Signature block containing signer info and reason
            password: Password for re-authentication (if method is 'password')
            actor_user_id: User attempting the action

        Returns:
            True if signature is valid

        Raises:
            SignatureVerificationException: If signature verification fails
        """
        if not signature:
            raise SignatureVerificationException("Signature block is required")

        # Verify signer matches actor
        if signature.get("signer_user_id") != actor_user_id:
            raise SignatureVerificationException("Signer does not match authenticated user")

        # Verify reauthentication
        reauth_method = signature.get("reauthentication_method")
        if reauth_method == "password":
            if not password:
                raise SignatureVerificationException("Password required for signature")

            # Verify password
            from services.auth import AuthService
            auth_service = AuthService(self.db)
            
            cursor = self.db.execute(
                "SELECT username FROM users WHERE user_id = ?",
                (actor_user_id,),
            )
            user_row = cursor.fetchone()
            if not user_row:
                raise SignatureVerificationException("User not found")

            if not auth_service.verify_password(user_row["username"], password):
                raise SignatureVerificationException("Password verification failed")

        elif reauth_method in ["mfa", "sso_reauth"]:
            # These would integrate with actual MFA/SSO systems
            # For now, we accept them as valid if present
            pass
        else:
            raise SignatureVerificationException(f"Unsupported reauthentication method: {reauth_method}")

        return True

    # PUBLIC_INTERFACE
    def enforce_segregation_of_duties(
        self,
        data_asset_id: str,
        approver_user_id: str,
    ) -> bool:
        """
        PUBLIC_INTERFACE
        Enforce Segregation of Duties: approver must not be the submitter.

        FR-APP-002: Implements SoD enforcement to prevent self-approval.

        Args:
            data_asset_id: Data asset identifier
            approver_user_id: User attempting approval

        Returns:
            True if SoD is satisfied

        Raises:
            SoDViolationException: If approver is the same as submitter
        """
        cursor = self.db.execute(
            "SELECT submitter_user_id FROM data_assets WHERE data_asset_id = ?",
            (data_asset_id,),
        )
        row = cursor.fetchone()

        if not row:
            raise ApprovalException(f"Data asset not found: {data_asset_id}")

        submitter_user_id = row["submitter_user_id"]

        if submitter_user_id == approver_user_id:
            raise SoDViolationException(
                "Segregation of Duties violation: submitter and approver must be different users"
            )

        return True

    # PUBLIC_INTERFACE
    def process_approval(
        self,
        data_asset_id: str,
        decision: str,
        signature: Optional[Dict[str, Any]],
        password: Optional[str],
        rationale: Optional[str],
        actor_user_id: str,
        actor_role: str,
        correlation_id: str,
        required_preconditions: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        PUBLIC_INTERFACE
        Process approval or rejection of a data asset.

        FR-APP-001: Validates electronic signature
        FR-APP-002: Enforces Segregation of Duties
        FR-APP-003: Generates evidence package on approval

        Args:
            data_asset_id: Data asset identifier
            decision: 'publish' or 'reject'
            signature: Electronic signature block
            password: Password for signature verification
            rationale: Optional rationale for decision
            actor_user_id: User making the decision
            actor_role: Role of the user
            correlation_id: Request correlation ID
            required_preconditions: Optional preconditions (e.g., validation run ID)

        Returns:
            Dictionary containing approval result and evidence package ID (if applicable)
        """
        # Fetch data asset
        cursor = self.db.execute(
            "SELECT * FROM data_assets WHERE data_asset_id = ?",
            (data_asset_id,),
        )
        data_asset_row = cursor.fetchone()

        if not data_asset_row:
            raise ApprovalException(f"Data asset not found: {data_asset_id}")

        data_asset = dict(data_asset_row)

        # Verify state allows approval
        if data_asset["state"] not in ["in_review", "validating"]:
            raise ApprovalException(f"Data asset state does not allow approval: {data_asset['state']}")

        # Enforce SoD
        self.enforce_segregation_of_duties(data_asset_id, actor_user_id)

        # Verify signature if provided
        if signature:
            self.verify_electronic_signature(signature, password, actor_user_id)

        # Check preconditions (e.g., validation must pass)
        if required_preconditions and decision == "publish":
            latest_validation = self.validation_service.get_latest_validation_for_data_asset(data_asset_id)
            
            if not latest_validation:
                raise ApprovalException("No validation run found for data asset")

            if latest_validation.get("overall_status") != "pass":
                raise ApprovalException("Cannot approve: validation status is not 'pass'")

            expected_val_id = required_preconditions.get("latest_validation_run_id")
            if expected_val_id and latest_validation.get("validation_run_id") != expected_val_id:
                raise ApprovalException("Validation run ID mismatch: stale validation state")

        # Create approval record
        approval_record_id = generate_id("apr")
        created_at_utc = utc_now_iso()
        signature_json = json.dumps(signature) if signature else None

        try:
            self.db.execute(
                """
                INSERT INTO approval_records(
                    approval_record_id, data_asset_id, decision,
                    approver_user_id, signature_json, created_at_utc
                ) VALUES(?,?,?,?,?,?)
                """,
                (approval_record_id, data_asset_id, decision, actor_user_id, signature_json, created_at_utc),
            )

            # Update data asset state
            new_state = "published" if decision == "publish" else "rejected"
            self.db.execute(
                "UPDATE data_assets SET state = ?, last_updated_at_utc = ? WHERE data_asset_id = ?",
                (new_state, created_at_utc, data_asset_id),
            )

            # Generate evidence package on approval
            evidence_package_id = None
            if decision == "publish":
                evidence_package = self.evidence_service.create_evidence_package(
                    data_asset_id=data_asset_id,
                    actor_user_id=actor_user_id,
                    actor_role=actor_role,
                    correlation_id=correlation_id,
                )
                evidence_package_id = evidence_package["evidence_package_id"]

            # Record audit event
            self.audit_service.record_event(
                event_type="data_asset_approved" if decision == "publish" else "data_asset_rejected",
                entity_type="data_asset",
                entity_id=data_asset_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                correlation_id=correlation_id,
                result="success",
                details={
                    "decision": decision,
                    "approval_record_id": approval_record_id,
                    "rationale": rationale,
                    "evidence_package_id": evidence_package_id,
                },
            )

            self.db.commit()

            return {
                "data_asset_id": data_asset_id,
                "state": new_state,
                "published_version_id": data_asset["package_version"] if decision == "publish" else None,
                "published_at_utc": created_at_utc if decision == "publish" else None,
                "evidence_package_id": evidence_package_id,
            }

        except Exception:
            self.db.rollback()
            raise
