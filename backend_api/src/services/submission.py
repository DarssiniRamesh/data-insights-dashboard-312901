"""
PUBLIC_INTERFACE
Submission service for managing data product submissions and workflow states.
"""
from typing import Dict, Any, Optional

from utils import generate_id, utc_now_iso
from services.audit import AuditService


class SubmissionService:
    """Service for submission lifecycle and state machine management."""

    def __init__(self, db_connection):
        self.db = db_connection
        self.audit_service = AuditService(db_connection)

    def create_submission(
        self,
        draft_id: str,
        actor_user_id: str,
        actor_role: str,
        correlation_id: str,
    ) -> Dict[str, Any]:
        """
        PUBLIC_INTERFACE
        Create a submission from a draft and queue validation job.
        """
        cursor = self.db.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,))
        draft_row = cursor.fetchone()
        if not draft_row:
            raise ValueError("Draft not found")

        draft = dict(draft_row)

        submission_id = generate_id("sub")
        state = "validating"
        created_at_utc = utc_now_iso()

        try:
            self.db.execute(
                """
                INSERT INTO submissions(
                    submission_id, draft_id, package_id, package_version, state,
                    submitter_user_id, created_at_utc, last_updated_at_utc, active_deviation_id
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    submission_id,
                    draft_id,
                    draft["package_id"],
                    draft["package_version"],
                    state,
                    actor_user_id,
                    created_at_utc,
                    created_at_utc,
                    None,
                ),
            )

            job_id = generate_id("job")
            self.db.execute(
                """
                INSERT INTO pipeline_jobs(
                    pipeline_job_id, submission_id, job_type, state, attempts, created_at_utc
                ) VALUES(?,?,?,?,?,?)
                """,
                (job_id, submission_id, "validate", "queued", 0, created_at_utc),
            )

            audit_event_id = self.audit_service.record_event(
                event_type="submission_created",
                entity_type="submission",
                entity_id=submission_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                correlation_id=correlation_id,
                result="success",
                details={"draft_id": draft_id, "package_id": draft["package_id"]},
            )

            self.audit_service.record_event(
                event_type="validation_job_queued",
                entity_type="pipeline_job",
                entity_id=job_id,
                actor_user_id="system",
                actor_role="system",
                correlation_id=correlation_id,
                result="success",
                details={"submission_id": submission_id, "job_type": "validate"},
            )

            self.db.commit()

            return {
                "submission_id": submission_id,
                "package_id": draft["package_id"],
                "package_version": draft["package_version"],
                "state": state,
                "created_at_utc": created_at_utc,
                "audit_event_id": audit_event_id,
            }

        except Exception:
            self.db.rollback()
            raise

    def get_submission(self, submission_id: str) -> Optional[Dict[str, Any]]:
        """
        PUBLIC_INTERFACE
        Get a submission by ID.
        """
        cursor = self.db.execute("SELECT * FROM submissions WHERE submission_id = ?", (submission_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_state(
        self,
        submission_id: str,
        new_state: str,
        actor_user_id: str,
        actor_role: str,
        correlation_id: str,
    ) -> None:
        """
        PUBLIC_INTERFACE
        Update submission state with audit logging.
        """
        updated_at = utc_now_iso()

        try:
            self.db.execute(
                "UPDATE submissions SET state = ?, last_updated_at_utc = ? WHERE submission_id = ?",
                (new_state, updated_at, submission_id),
            )

            self.audit_service.record_event(
                event_type="submission_state_changed",
                entity_type="submission",
                entity_id=submission_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                correlation_id=correlation_id,
                result="success",
                details={"new_state": new_state},
            )

            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
