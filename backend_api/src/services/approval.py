"""
PUBLIC_INTERFACE
Approval service for managing submission approvals with SoD and e-sign validation.
"""
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from utils import generate_id, utc_now_iso, compute_hash
from services.audit import AuditService
from services.evidence import EvidenceService


class ApprovalError(Exception):
    """Base exception for approval errors."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class AuthenticationError(ApprovalError):
    """Authentication failure."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("AUTHENTICATION_FAILED", message, details)


class AuthorizationError(ApprovalError):
    """Authorization failure."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("AUTHORIZATION_FAILED", message, details)


class SoDViolationError(ApprovalError):
    """Segregation of Duties violation."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("SOD_VIOLATION", message, details)


class SignatureError(ApprovalError):
    """Electronic signature validation failure."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("SIGNATURE_VALIDATION_FAILED", message, details)


class InvalidStateError(ApprovalError):
    """Invalid workflow state transition."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("INVALID_STATE_TRANSITION", message, details)


class ApprovalService:
    """
    Service for approval workflow with SoD enforcement and electronic signature validation.
    """

    VALID_TRANSITIONS = {
        "validating": ["failed_validation", "in_review"],
        "failed_validation": ["remediating"],
        "in_review": ["approved", "rejected", "remediating"],
        "remediating": ["validating"],
        "approved": ["published"],
        "published": [],
        "rejected": [],
    }

    APPROVER_ROLES = ["approver", "admin", "steward", "governance_admin"]
    SIGNATURE_WINDOW_MINUTES = 5

    def __init__(self, db_connection):
        self.db = db_connection
        self.audit_service = AuditService(db_connection)
        self.evidence_service = EvidenceService(db_connection)

    def verify_esign(
        self,
        user_id: str,
        password: str,
        intent: str,
        signature_block: Dict[str, Any],
        correlation_id: str,
    ) -> Dict[str, Any]:
        """
        PUBLIC_INTERFACE
        Verify electronic signature credentials and create signed record.
        """
        from services.auth import AuthService
        auth_service = AuthService(self.db)

        cursor = self.db.execute(
            "SELECT user_id, password_hash, password_salt, roles FROM users WHERE user_id = ?",
            (user_id,),
        )
        user_row = cursor.fetchone()
        if not user_row:
            raise AuthenticationError(f"User {user_id} not found", {"user_id": user_id})

        if password:
            if not auth_service.verify_password(password, user_row["password_hash"], user_row["password_salt"]):
                raise AuthenticationError("Invalid password for electronic signature", {"user_id": user_id})

        required_fields = ["signer_user_id", "signer_role", "signed_at_utc", "reauthentication_method", "signature_reason"]
        for field in required_fields:
            if field not in signature_block:
                raise SignatureError(f"Missing required signature field: {field}", {"missing_field": field})

        if signature_block["signer_user_id"] != user_id:
            raise SignatureError(
                "Signature signer_user_id does not match authenticated user",
                {"expected": user_id, "provided": signature_block["signer_user_id"]},
            )

        signed_at = signature_block["signed_at_utc"]
        current_time = datetime.now(timezone.utc)
        try:
            signed_time = datetime.fromisoformat(signed_at.replace("Z", "+00:00"))
            time_diff = abs((current_time - signed_time).total_seconds() / 60)
            if time_diff > self.SIGNATURE_WINDOW_MINUTES:
                raise SignatureError(
                    f"Signature timestamp outside allowed window ({self.SIGNATURE_WINDOW_MINUTES} minutes)",
                    {"signed_at_utc": signed_at, "current_utc": utc_now_iso(), "window_minutes": self.SIGNATURE_WINDOW_MINUTES},
                )
        except (ValueError, AttributeError) as e:
            raise SignatureError("Invalid signature timestamp format", {"signed_at_utc": signed_at, "error": str(e)})

        signature_content = {"intent": intent, "signer_user_id": user_id, "signed_at_utc": signed_at, "signature_reason": signature_block["signature_reason"]}
        signature_hash = compute_hash(signature_content)

        verified_signature = signature_block.copy()
        verified_signature["signature_hash"] = signature_hash
        verified_signature["verified_at_utc"] = utc_now_iso()
        return verified_signature

    def approve_submission(
        self,
        submission_id: str,
        decision: str,
        approver_user_id: str,
        approver_role: str,
        signature: Dict[str, Any],
        correlation_id: str,
        required_preconditions: Optional[Dict[str, Any]] = None,
        rationale: Optional[str] = None,
        password_for_esign: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        PUBLIC_INTERFACE
        Approve or reject a submission with SoD and e-sign validation.
        """
        if decision not in ["publish", "reject"]:
            raise ApprovalError("INVALID_DECISION", f"Decision must be 'publish' or 'reject', got '{decision}'")

        if approver_role not in self.APPROVER_ROLES:
            raise AuthorizationError(
                f"Role '{approver_role}' not authorized to approve submissions",
                {"user_role": approver_role, "required_roles": self.APPROVER_ROLES},
            )

        cursor = self.db.execute("SELECT * FROM submissions WHERE submission_id = ?", (submission_id,))
        submission_row = cursor.fetchone()
        if not submission_row:
            raise ApprovalError("SUBMISSION_NOT_FOUND", f"Submission {submission_id} not found")
        submission = dict(submission_row)

        current_state = submission["state"]
        if current_state not in ["in_review"]:
            raise InvalidStateError("Cannot approve submission in current state", {"current_state": current_state, "required_state": "in_review"})

        if approver_user_id == submission["submitter_user_id"]:
            self.audit_service.record_event(
                event_type="approval_blocked_sod_violation",
                entity_type="submission",
                entity_id=submission_id,
                actor_user_id=approver_user_id,
                actor_role=approver_role,
                correlation_id=correlation_id,
                result="blocked",
                details={"reason": "Same user cannot submit and approve", "submitter_user_id": submission["submitter_user_id"], "approver_user_id": approver_user_id},
            )
            self.db.commit()
            raise SoDViolationError("Submitter cannot approve their own submission", {"submitter_user_id": submission["submitter_user_id"], "approver_user_id": approver_user_id})

        if not signature:
            raise SignatureError("Electronic signature required for approval", {"submission_id": submission_id})

        # Identity binding: signer must be the authenticated approver.
        if signature.get("signer_user_id") and signature.get("signer_user_id") != approver_user_id:
            raise SignatureError(
                "Signature signer_user_id does not match authenticated user",
                {"expected": approver_user_id, "provided": signature.get("signer_user_id")},
            )

        # Timestamp window policy (+/- SIGNATURE_WINDOW_MINUTES, using audit_context time as "now").
        signed_at = signature.get("signed_at_utc")
        if not signed_at:
            raise SignatureError("Missing signed_at_utc in signature block", {"missing_field": "signed_at_utc"})
        try:
            signed_time = datetime.fromisoformat(str(signed_at).replace("Z", "+00:00"))
            now_utc = datetime.now(timezone.utc)
            diff_min = abs((now_utc - signed_time).total_seconds()) / 60.0
            if diff_min > self.SIGNATURE_WINDOW_MINUTES:
                raise SignatureError(
                    f"Signature timestamp outside allowed window ({self.SIGNATURE_WINDOW_MINUTES} minutes)",
                    {"signed_at_utc": signed_at, "current_utc": utc_now_iso(), "window_minutes": self.SIGNATURE_WINDOW_MINUTES},
                )
        except SignatureError:
            raise
        except Exception as e:
            raise SignatureError("Invalid signature timestamp format", {"signed_at_utc": signed_at, "error": str(e)})

        if signature.get("reauthentication_method") == "password":
            if not password_for_esign:
                raise SignatureError("Password re-entry required for electronic signature", {"reauthentication_method": "password"})
            from services.auth import AuthService

            auth_service = AuthService(self.db)
            cursor = self.db.execute("SELECT password_hash, password_salt FROM users WHERE user_id = ?", (approver_user_id,))
            user_row = cursor.fetchone()
            if not user_row:
                raise AuthenticationError("Approver user not found", {"approver_user_id": approver_user_id})
            if not auth_service.verify_password(password_for_esign, user_row["password_hash"], user_row["password_salt"]):
                raise SignatureError("Invalid password for electronic signature", {})

        # Hash check (when provided) must match canonical expected intent payload.
        if "signature_hash" in signature and signature.get("signature_hash") is not None:
            expected_content = {
                "intent": f"approve_submission_{submission_id}",
                "signer_user_id": signature.get("signer_user_id"),
                "signed_at_utc": signature.get("signed_at_utc"),
                "signature_reason": signature.get("signature_reason"),
            }
            expected_hash = compute_hash(expected_content)
            if signature["signature_hash"] != expected_hash:
                raise SignatureError(
                    "Signature hash validation failed",
                    {"expected_hash": expected_hash, "provided_hash": signature["signature_hash"]},
                )

        if required_preconditions and "latest_validation_run_id" in required_preconditions:
            cursor = self.db.execute(
                """
                SELECT validation_run_id, overall_status
                FROM validation_runs
                WHERE submission_id = ?
                ORDER BY created_at_utc DESC
                LIMIT 1
                """,
                (submission_id,),
            )
            validation_row = cursor.fetchone()
            if not validation_row:
                raise ApprovalError("PRECONDITION_NOT_MET", "No validation run found for submission")
            validation = dict(validation_row)
            if validation["validation_run_id"] != required_preconditions["latest_validation_run_id"]:
                raise ApprovalError("PRECONDITION_NOT_MET", "Validation run ID does not match latest", {"expected": required_preconditions["latest_validation_run_id"], "actual": validation["validation_run_id"]})
            if decision == "publish" and validation["overall_status"] != "pass":
                raise ApprovalError("PRECONDITION_NOT_MET", "Cannot approve for publish when validation failed", {"validation_status": validation["overall_status"]})

        new_state = "approved" if decision == "publish" else "rejected"

        try:
            approval_record_id = generate_id("approval")
            created_at_utc = utc_now_iso()
            signature_json = json.dumps(signature)

            self.db.execute(
                """
                INSERT INTO approval_records(
                    approval_record_id, submission_id, decision, approver_user_id,
                    signature_json, created_at_utc
                ) VALUES(?,?,?,?,?,?)
                """,
                (approval_record_id, submission_id, decision, approver_user_id, signature_json, created_at_utc),
            )

            self.db.execute(
                "UPDATE submissions SET state = ?, last_updated_at_utc = ? WHERE submission_id = ?",
                (new_state, created_at_utc, submission_id),
            )

            self.audit_service.record_event(
                event_type="submission_approved" if decision == "publish" else "submission_rejected",
                entity_type="submission",
                entity_id=submission_id,
                actor_user_id=approver_user_id,
                actor_role=approver_role,
                correlation_id=correlation_id,
                result="success",
                details={"decision": decision, "approval_record_id": approval_record_id, "new_state": new_state, "rationale": rationale},
            )

            evidence_package_id = None
            if decision == "publish":
                evidence_items = [
                    {
                        "type": "approval_record",
                        "content": {
                            "approval_record_id": approval_record_id,
                            "submission_id": submission_id,
                            "decision": decision,
                            "approver_user_id": approver_user_id,
                            "signature": signature,
                            "created_at_utc": created_at_utc,
                            "rationale": rationale,
                        },
                    }
                ]

                if required_preconditions and "latest_validation_run_id" in required_preconditions:
                    val_run_id = required_preconditions["latest_validation_run_id"]
                    cursor = self.db.execute(
                        """
                        SELECT vr.*, a.storage_ref
                        FROM validation_runs vr
                        JOIN artifacts a ON vr.report_artifact_id = a.artifact_id
                        WHERE vr.validation_run_id = ?
                        """,
                        (val_run_id,),
                    )
                    val_row = cursor.fetchone()
                    if val_row:
                        storage_ref = val_row["storage_ref"]
                        if os.path.exists(storage_ref):
                            with open(storage_ref, "r") as f:
                                validation_report = json.load(f)
                            evidence_items.append({"type": "validation_report", "content": validation_report})

                evidence_result = self.evidence_service.create_evidence_package(
                    submission_id=submission_id,
                    package_id=submission["package_id"],
                    package_version=submission["package_version"],
                    evidence_items=evidence_items,
                    actor_user_id="system",
                    actor_role="system",
                    correlation_id=correlation_id,
                )
                evidence_package_id = evidence_result["evidence_package_id"]

                self.evidence_service.link_evidence_to_approval(
                    evidence_package_id=evidence_package_id,
                    approval_record_id=approval_record_id,
                    actor_user_id="system",
                    actor_role="system",
                    correlation_id=correlation_id,
                )

            self.db.commit()

            result = {
                "submission_id": submission_id,
                "state": new_state,
                "approval_record_id": approval_record_id,
                "approved_at_utc": created_at_utc,
                "decision": decision,
            }

            if decision == "publish":
                result["published_version_id"] = f"{submission['package_id']}-{submission['package_version']}"
                result["published_at_utc"] = created_at_utc
                result["evidence_package_id"] = evidence_package_id

            return result

        except Exception:
            self.db.rollback()
            raise

    def _add_minutes_to_iso(self, iso_timestamp: str, minutes: int) -> str:
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        dt_new = dt + timedelta(minutes=minutes)
        return dt_new.isoformat().replace("+00:00", "Z")
