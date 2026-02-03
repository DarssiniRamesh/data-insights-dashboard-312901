"""
PUBLIC_INTERFACE
Audit service for recording audit events with transactional coupling.

Implements:
- FR-AUD-001: Comprehensive audit logging with actor, timestamp, and result
- FR-AUD-002: Audit trail immutability (append-only design)
- FR-AUD-003: Audit query access control (enforced at router level)
- FR-DPP-003: Identity capture for all actions
"""
import json
from typing import Dict, Any, Optional
from utils import generate_id, utc_now_iso


class AuditService:
    """
    Service for managing audit trail with fail-closed transactional behavior.
    """
    
    def __init__(self, db_connection):
        self.db = db_connection
    
    def record_event(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str,
        actor_user_id: str,
        actor_role: str,
        correlation_id: str,
        result: str = "success",
        details: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        PUBLIC_INTERFACE
        Record an audit event.
        
        Args:
            event_type: Type of event (e.g., 'draft_created', 'submission_created')
            entity_type: Type of entity (e.g., 'draft', 'submission')
            entity_id: ID of the entity
            actor_user_id: User performing the action
            actor_role: Role of the actor
            correlation_id: Request correlation ID
            result: Result of the action ('success', 'failure', 'blocked')
            details: Additional details (will be serialized to JSON)
            
        Returns:
            audit_event_id
            
        Raises:
            Exception: If audit insert fails (caller must rollback transaction)
        """
        audit_event_id = generate_id("audit")
        timestamp_utc = utc_now_iso()
        details_json = json.dumps(details) if details else None
        
        self.db.execute(
            """
            INSERT INTO audit_events(
                audit_event_id, event_type, entity_type, entity_id,
                actor_user_id, actor_role, timestamp_utc, correlation_id,
                result, details_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                audit_event_id, event_type, entity_type, entity_id,
                actor_user_id, actor_role, timestamp_utc, correlation_id,
                result, details_json
            )
        )
        
        return audit_event_id
    
    def query_events(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        limit: int = 100
    ) -> list:
        """
        PUBLIC_INTERFACE
        Query audit events.
        
        Args:
            entity_type: Filter by entity type
            entity_id: Filter by entity ID
            limit: Maximum number of events to return
            
        Returns:
            List of audit event dicts
        """
        query = "SELECT * FROM audit_events WHERE 1=1"
        params = []
        
        if entity_type:
            query += " AND entity_type = ?"
            params.append(entity_type)
        
        if entity_id:
            query += " AND entity_id = ?"
            params.append(entity_id)
        
        query += " ORDER BY timestamp_utc ASC LIMIT ?"
        params.append(limit)
        
        cursor = self.db.execute(query, params)
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]
