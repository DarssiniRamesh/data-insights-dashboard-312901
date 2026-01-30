"""
PUBLIC_INTERFACE
Draft service for managing data product drafts.
"""
import json
from typing import Dict, Any
from src.utils import generate_id, utc_now_iso
from src.services.audit import AuditService


class DraftService:
    """
    Service for draft lifecycle management.
    """
    
    def __init__(self, db_connection):
        self.db = db_connection
        self.audit_service = AuditService(db_connection)
    
    def create_draft(
        self,
        package: Dict[str, Any],
        actor_user_id: str,
        actor_role: str,
        correlation_id: str
    ) -> Dict[str, Any]:
        """
        PUBLIC_INTERFACE
        Create a new draft with transactional audit logging.
        
        Args:
            package: Data product package definition
            actor_user_id: User creating the draft
            actor_role: Role of the actor
            correlation_id: Request correlation ID
            
        Returns:
            Dict with draft_id, package_id, package_version, state, created_at_utc, audit_event_id
            
        Raises:
            Exception: If draft or audit insert fails (transaction will rollback)
        """
        draft_id = generate_id("draft")
        package_id = package.get("product", {}).get("name", "unknown")
        package_version = "1.0.0-draft.1"
        state = "draft"
        created_at_utc = utc_now_iso()
        package_json = json.dumps(package)
        
        try:
            # Insert draft
            self.db.execute(
                """
                INSERT INTO drafts(
                    draft_id, package_id, package_version, state, package_json,
                    created_by_user_id, created_at_utc, updated_at_utc
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    draft_id, package_id, package_version, state, package_json,
                    actor_user_id, created_at_utc, created_at_utc
                )
            )
            
            # Record audit event
            audit_event_id = self.audit_service.record_event(
                event_type="draft_created",
                entity_type="draft",
                entity_id=draft_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                correlation_id=correlation_id,
                result="success",
                details={"package_id": package_id, "package_version": package_version}
            )
            
            # Commit transaction
            self.db.commit()
            
            return {
                "draft_id": draft_id,
                "package_id": package_id,
                "package_version": package_version,
                "state": state,
                "created_at_utc": created_at_utc,
                "audit_event_id": audit_event_id
            }
        
        except Exception as e:
            # Rollback on any failure (fail-closed)
            self.db.rollback()
            raise
    
    def get_draft(self, draft_id: str) -> Optional[Dict[str, Any]]:
        """
        PUBLIC_INTERFACE
        Get a draft by ID.
        
        Args:
            draft_id: Draft identifier
            
        Returns:
            Draft dict or None if not found
        """
        cursor = self.db.execute(
            "SELECT * FROM drafts WHERE draft_id = ?",
            (draft_id,)
        )
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
