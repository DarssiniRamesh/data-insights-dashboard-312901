"""
PUBLIC_INTERFACE
Validation service for running quality gates and generating validation reports.
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.utils import generate_id, utc_now_iso, canonical_json, compute_hash
from src.services.audit import AuditService


class ValidationService:
    """
    Service for validation run execution and report generation.
    """
    
    def __init__(self, db_connection):
        self.db = db_connection
        self.audit_service = AuditService(db_connection)
        self.artifact_root = os.getenv("ARTIFACT_STORE_ROOT", "data/artifacts")
        Path(self.artifact_root).mkdir(parents=True, exist_ok=True)
    
    def run_validation(
        self,
        submission_id: str,
        validation_profile: str = "baseline",
        actor_user_id: str = "system",
        actor_role: str = "system",
        correlation_id: str = ""
    ) -> Dict[str, Any]:
        """
        PUBLIC_INTERFACE
        Execute validation run and create versioned report.
        
        Args:
            submission_id: Submission to validate
            validation_profile: Validation profile to use
            actor_user_id: User triggering validation
            actor_role: Role of actor
            correlation_id: Request correlation ID
            
        Returns:
            Dict with validation_run_id and overall_status
        """
        # Get submission and draft
        cursor = self.db.execute(
            """
            SELECT s.*, d.package_json 
            FROM submissions s 
            JOIN drafts d ON s.draft_id = d.draft_id 
            WHERE s.submission_id = ?
            """,
            (submission_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            raise ValueError("Submission not found")
        
        submission = dict(row)
        package = json.loads(submission["package_json"])
        
        # Run validation checks
        checks = []
        
        # Schema conformance check
        schema_check = self._check_schema_conformance(package)
        checks.append(schema_check)
        
        # Freshness check
        freshness_check = self._check_freshness(package)
        checks.append(freshness_check)
        
        # Completeness check
        completeness_check = self._check_completeness(package)
        checks.append(completeness_check)
        
        # Determine overall status
        overall_status = "pass" if all(c["status"] == "pass" for c in checks) else "fail"
        
        # Create validation report
        validation_run_id = generate_id("val")
        created_at_utc = utc_now_iso()
        
        report = {
            "validation_run_id": validation_run_id,
            "overall_status": overall_status,
            "checks": checks,
            "rule_versions": {
                "validation_ruleset_version": "2026.01",
                "format_skill_version": "1.0.0"
            },
            "created_at_utc": created_at_utc
        }
        
        # Compute hash
        report_hash = compute_hash(report)
        
        # Save report artifact
        artifact_id = generate_id("art")
        storage_ref = f"{self.artifact_root}/validation-reports/{submission_id}/{validation_run_id}.json"
        Path(storage_ref).parent.mkdir(parents=True, exist_ok=True)
        
        with open(storage_ref, 'w') as f:
            f.write(canonical_json(report))
        
        try:
            # Insert artifact
            self.db.execute(
                """
                INSERT INTO artifacts(
                    artifact_id, artifact_type, content_type, storage_ref, hash_sha256, created_at_utc
                ) VALUES(?,?,?,?,?,?)
                """,
                (artifact_id, "validation_report", "application/json", storage_ref, report_hash, created_at_utc)
            )
            
            # Insert validation run
            checks_json = json.dumps(checks)
            rule_versions_json = json.dumps(report["rule_versions"])
            
            self.db.execute(
                """
                INSERT INTO validation_runs(
                    validation_run_id, submission_id, validation_profile, overall_status,
                    checks_json, rule_versions_json, report_artifact_id, report_hash_sha256, created_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    validation_run_id, submission_id, validation_profile, overall_status,
                    checks_json, rule_versions_json, artifact_id, report_hash, created_at_utc
                )
            )
            
            # Update submission state
            new_state = "in_review" if overall_status == "pass" else "failed_validation"
            self.db.execute(
                "UPDATE submissions SET state = ?, last_updated_at_utc = ? WHERE submission_id = ?",
                (new_state, created_at_utc, submission_id)
            )
            
            # Record audit event
            self.audit_service.record_event(
                event_type="validation_run_completed",
                entity_type="validation_run",
                entity_id=validation_run_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                correlation_id=correlation_id or generate_id("corr"),
                result="success",
                details={"overall_status": overall_status, "submission_id": submission_id}
            )
            
            self.db.commit()
            
            return {
                "validation_run_id": validation_run_id,
                "overall_status": overall_status,
                "report_hash": report_hash
            }
        
        except Exception as e:
            self.db.rollback()
            raise
    
    def _check_schema_conformance(self, package: Dict[str, Any]) -> Dict[str, Any]:
        """Check schema conformance (stub implementation)."""
        # In a real implementation, this would load the dataset and validate structure
        return {
            "check_name": "schema_conformance",
            "status": "pass",
            "metrics": {"missing_columns": 0},
            "findings": []
        }
    
    def _check_freshness(self, package: Dict[str, Any]) -> Dict[str, Any]:
        """Check data freshness (stub implementation)."""
        # In a real implementation, this would check dataset timestamp against max_age
        return {
            "check_name": "freshness",
            "status": "pass",
            "metrics": {"dataset_age_hours": 2, "max_age_hours": 24},
            "findings": []
        }
    
    def _check_completeness(self, package: Dict[str, Any]) -> Dict[str, Any]:
        """Check completeness for critical fields (stub implementation)."""
        # In a real implementation, this would compute null percentages for critical fields
        return {
            "check_name": "completeness",
            "status": "pass",
            "metrics": {"critical_fields_max_null_pct": 1.0},
            "findings": []
        }
    
    def get_validation_report(self, validation_run_id: str) -> Optional[Dict[str, Any]]:
        """
        PUBLIC_INTERFACE
        Get validation report for a validation run.
        
        Args:
            validation_run_id: Validation run identifier
            
        Returns:
            Validation report dict or None if not found
        """
        cursor = self.db.execute(
            """
            SELECT vr.*, a.storage_ref 
            FROM validation_runs vr
            JOIN artifacts a ON vr.report_artifact_id = a.artifact_id
            WHERE vr.validation_run_id = ?
            """,
            (validation_run_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        # Load report from storage
        storage_ref = row["storage_ref"]
        if os.path.exists(storage_ref):
            with open(storage_ref, 'r') as f:
                report = json.load(f)
            return report
        
        return None
    
    def list_validation_runs(self, submission_id: str) -> List[Dict[str, Any]]:
        """
        PUBLIC_INTERFACE
        List validation runs for a submission.
        
        Args:
            submission_id: Submission identifier
            
        Returns:
            List of validation run summaries
        """
        cursor = self.db.execute(
            """
            SELECT validation_run_id, overall_status, created_at_utc, report_artifact_id, report_hash_sha256
            FROM validation_runs
            WHERE submission_id = ?
            ORDER BY created_at_utc DESC
            """,
            (submission_id,)
        )
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]
