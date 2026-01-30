"""
PUBLIC_INTERFACE
Draft service for managing draft data product packages.
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
        Create a new draft data product package.
        
        Args:
            package: Package data (product, dataset, controls, etc.)
            actor_user_id: User creating the draft
            actor_role: Role of the actor
            correlation_id: Request correlation ID
            
        Returns:
            Dict with draft_id, package_id, package_version, state, created_at_utc
            
        Raises:
            ValueError: If package invalid
            Exception: If transaction fails
        """
        # Validate package structure
        if "product" not in package:
            raise ValueError("Package must include 'product' metadata")
        
        if "dataset" not in package:
            raise ValueError("Package must include 'dataset' reference")
        
        if "controls" not in package:
            raise ValueError("Package must include 'controls' metadata")
        
        # Extract package ID and version
        product = package["product"]
        package_id = product.get("name", f"pkg-{generate_id('pkg')}")
        
        # Determine version
        if "package_version" in package:
            package_version = package["package_version"]
        else:
            # Auto-increment version based on existing drafts/submissions
            cursor = self.db.execute(
                "SELECT MAX(package_version) as max_ver FROM drafts WHERE package_id = ?",
                (package_id,)
            )
            row = cursor.fetchone()
            max_ver = row["max_ver"] if row and row["max_ver"] else "0.0.0"
            
            # Simple version increment (in production, use semantic versioning)
            parts = max_ver.split(".")
            patch = int(parts[2]) + 1 if len(parts) == 3 else 1
            package_version = f"{parts[0]}.{parts[1]}.{patch}" if len(parts) >= 2 else f"0.0.{patch}"
        
        draft_id = generate_id("draft")
        state = "draft"
        created_at_utc = utc_now_iso()
        
        try:
            # Store draft
            self.db.execute(
                """
                INSERT INTO drafts(
                    draft_id, package_id, package_version, state, package_json,
                    created_by_user_id, created_at_utc, updated_at_utc
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    draft_id, package_id, package_version, state, json.dumps(package),
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
            self.db.rollback()
            raise
    
    def get_draft(self, draft_id: str) -> Dict[str, Any]:
        """
        PUBLIC_INTERFACE
        Get a draft by ID.
        
        Args:
            draft_id: Draft identifier
            
        Returns:
            Draft dict with package data
            
        Raises:
            ValueError: If draft not found
        """
        cursor = self.db.execute(
            "SELECT * FROM drafts WHERE draft_id = ?",
            (draft_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            raise ValueError(f"Draft {draft_id} not found")
        
        draft = dict(row)
        draft["package"] = json.loads(draft["package_json"])
        
        return draft
    
    def list_drafts(self, user_id: str = None) -> list:
        """
        PUBLIC_INTERFACE
        List drafts, optionally filtered by user.
        
        Args:
            user_id: Optional user ID to filter by
            
        Returns:
            List of draft dicts
        """
        if user_id:
            cursor = self.db.execute(
                "SELECT * FROM drafts WHERE created_by_user_id = ? ORDER BY created_at_utc DESC",
                (user_id,)
            )
        else:
            cursor = self.db.execute(
                "SELECT * FROM drafts ORDER BY created_at_utc DESC"
            )
        
        rows = cursor.fetchall()
        drafts = []
        for row in rows:
            draft = dict(row)
            draft["package"] = json.loads(draft["package_json"])
            drafts.append(draft)
        
        return drafts
