"""
PUBLIC_INTERFACE
Evidence package service for managing audit-linked JSON evidence with hashing.

Implements:
- FR-EVD-001: Tamper-evident evidence package creation
- FR-EVD-002: Cryptographic hashing (SHA-256) of all evidence artifacts
- FR-EVD-003: Evidence integrity verification on retrieval
- FR-EVD-004: Evidence-approval linkage via audit trail
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List

from utils import generate_id, utc_now_iso, canonical_json, compute_hash
from services.audit import AuditService


class EvidenceError(Exception):
    """Base exception for evidence errors."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class EvidenceService:
    """Service for evidence package management with hashing and audit linkage."""

    def __init__(self, db_connection):
        self.db = db_connection
        self.audit_service = AuditService(db_connection)
        self.artifact_root = os.getenv("ARTIFACT_STORE_ROOT", "data/artifacts")
        Path(self.artifact_root).mkdir(parents=True, exist_ok=True)

    def create_evidence_package(
        self,
        submission_id: str,
        package_id: str,
        package_version: str,
        evidence_items: List[Dict[str, Any]],
        actor_user_id: str = "system",
        actor_role: str = "system",
        correlation_id: str = "",
    ) -> Dict[str, Any]:
        """
        PUBLIC_INTERFACE
        Create an evidence package with manifest and linked artifacts.
        """
        cursor = self.db.execute("SELECT submission_id, state FROM submissions WHERE submission_id = ?", (submission_id,))
        if not cursor.fetchone():
            raise EvidenceError("SUBMISSION_NOT_FOUND", f"Submission {submission_id} not found")

        evidence_package_id = generate_id("evid")
        created_at_utc = utc_now_iso()
        minted_identifier = f"urn:evidence:{package_id}:{package_version}:{evidence_package_id}"

        artifacts: List[Dict[str, Any]] = []

        try:
            for idx, evidence_item in enumerate(evidence_items):
                artifact_id = generate_id("art")
                evidence_type = evidence_item.get("type", "evidence_json")
                evidence_content = evidence_item.get("content", {})

                content_hash = compute_hash(evidence_content)

                storage_ref = f"{self.artifact_root}/evidence/{submission_id}/{evidence_package_id}-{idx}.json"
                Path(storage_ref).parent.mkdir(parents=True, exist_ok=True)
                with open(storage_ref, "w") as f:
                    f.write(canonical_json(evidence_content))

                self.db.execute(
                    """
                    INSERT INTO artifacts(
                        artifact_id, artifact_type, content_type, storage_ref, hash_sha256, created_at_utc
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (artifact_id, evidence_type, "application/json", storage_ref, content_hash, created_at_utc),
                )

                artifacts.append({"artifact_id": artifact_id, "artifact_type": evidence_type, "hash_sha256": content_hash, "storage_ref": storage_ref})

            manifest = {
                "evidence_package_id": evidence_package_id,
                "package_id": package_id,
                "package_version": package_version,
                "submission_id": submission_id,
                "minted_identifier": minted_identifier,
                "artifacts": artifacts,
                "created_at_utc": created_at_utc,
            }

            manifest_hash = compute_hash(manifest)

            manifest_artifact_id = generate_id("art")
            manifest_storage_ref = f"{self.artifact_root}/evidence-manifests/{submission_id}/{evidence_package_id}.json"
            Path(manifest_storage_ref).parent.mkdir(parents=True, exist_ok=True)
            with open(manifest_storage_ref, "w") as f:
                f.write(canonical_json(manifest))

            self.db.execute(
                """
                INSERT INTO artifacts(
                    artifact_id, artifact_type, content_type, storage_ref, hash_sha256, created_at_utc
                ) VALUES(?,?,?,?,?,?)
                """,
                (manifest_artifact_id, "evidence_manifest", "application/json", manifest_storage_ref, manifest_hash, created_at_utc),
            )

            self.db.execute(
                """
                INSERT INTO evidence_packages(
                    evidence_package_id, submission_id, package_id, package_version,
                    minted_identifier, manifest_artifact_id, created_at_utc
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (evidence_package_id, submission_id, package_id, package_version, minted_identifier, manifest_artifact_id, created_at_utc),
            )

            self.audit_service.record_event(
                event_type="evidence_package_created",
                entity_type="evidence_package",
                entity_id=evidence_package_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                correlation_id=correlation_id or generate_id("corr"),
                result="success",
                details={
                    "submission_id": submission_id,
                    "package_id": package_id,
                    "package_version": package_version,
                    "artifact_count": len(artifacts),
                    "manifest_hash": manifest_hash,
                },
            )

            self.db.commit()
            return {
                "evidence_package_id": evidence_package_id,
                "minted_identifier": minted_identifier,
                "manifest_artifact_id": manifest_artifact_id,
                "manifest_hash": manifest_hash,
                "artifacts": artifacts,
                "created_at_utc": created_at_utc,
            }

        except Exception as e:
            self.db.rollback()
            raise EvidenceError("EVIDENCE_CREATION_FAILED", f"Failed to create evidence package: {str(e)}", {"submission_id": submission_id, "error": str(e)})

    def get_evidence_package(self, evidence_package_id: str) -> Optional[Dict[str, Any]]:
        """
        PUBLIC_INTERFACE
        Get evidence package by ID with manifest and artifacts.
        """
        cursor = self.db.execute(
            """
            SELECT ep.*, a.storage_ref, a.hash_sha256 as manifest_hash
            FROM evidence_packages ep
            JOIN artifacts a ON ep.manifest_artifact_id = a.artifact_id
            WHERE ep.evidence_package_id = ?
            """,
            (evidence_package_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        package = dict(row)
        manifest_storage_ref = package["storage_ref"]

        if os.path.exists(manifest_storage_ref):
            with open(manifest_storage_ref, "r") as f:
                manifest = json.load(f)

            computed_hash = compute_hash(manifest)
            if computed_hash != package["manifest_hash"]:
                raise EvidenceError(
                    "EVIDENCE_INTEGRITY_VIOLATION",
                    "Manifest hash mismatch - evidence may be tampered",
                    {"evidence_package_id": evidence_package_id, "expected_hash": package["manifest_hash"], "computed_hash": computed_hash},
                )

            return {
                "evidence_package_id": package["evidence_package_id"],
                "package_id": package["package_id"],
                "package_version": package["package_version"],
                "minted_identifier": package["minted_identifier"],
                "manifest": manifest,
                "created_at_utc": package["created_at_utc"],
            }

        return None

    def get_evidence_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        """
        PUBLIC_INTERFACE
        Get evidence artifact by ID with integrity verification.
        """
        cursor = self.db.execute("SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,))
        row = cursor.fetchone()
        if not row:
            return None

        artifact = dict(row)
        storage_ref = artifact["storage_ref"]
        if not os.path.exists(storage_ref):
            return None

        with open(storage_ref, "r") as f:
            content = json.load(f)

        computed_hash = compute_hash(content)
        if computed_hash != artifact["hash_sha256"]:
            raise EvidenceError(
                "EVIDENCE_INTEGRITY_VIOLATION",
                "Artifact hash mismatch - evidence may be tampered",
                {"artifact_id": artifact_id, "expected_hash": artifact["hash_sha256"], "computed_hash": computed_hash},
            )

        return {
            "artifact_id": artifact["artifact_id"],
            "artifact_type": artifact["artifact_type"],
            "content_type": artifact["content_type"],
            "hash_sha256": artifact["hash_sha256"],
            "content": content,
            "created_at_utc": artifact["created_at_utc"],
        }

    def link_evidence_to_approval(
        self,
        evidence_package_id: str,
        approval_record_id: str,
        actor_user_id: str,
        actor_role: str,
        correlation_id: str,
    ) -> None:
        """
        PUBLIC_INTERFACE
        Create audit linkage between evidence package and approval record.
        """
        cursor = self.db.execute("SELECT evidence_package_id FROM evidence_packages WHERE evidence_package_id = ?", (evidence_package_id,))
        if not cursor.fetchone():
            raise EvidenceError("EVIDENCE_NOT_FOUND", f"Evidence package {evidence_package_id} not found")

        cursor = self.db.execute("SELECT approval_record_id FROM approval_records WHERE approval_record_id = ?", (approval_record_id,))
        if not cursor.fetchone():
            raise EvidenceError("APPROVAL_NOT_FOUND", f"Approval record {approval_record_id} not found")

        self.audit_service.record_event(
            event_type="evidence_linked_to_approval",
            entity_type="evidence_package",
            entity_id=evidence_package_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            correlation_id=correlation_id,
            result="success",
            details={"approval_record_id": approval_record_id, "evidence_package_id": evidence_package_id},
        )
        self.db.commit()
