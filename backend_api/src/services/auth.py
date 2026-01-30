"""
PUBLIC_INTERFACE
Authentication service stub for Bearer token validation.
"""
from typing import Optional, Dict, Any
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


security = HTTPBearer(auto_error=False)


class AuthService:
    """
    Simple Bearer token authentication service.
    
    In this implementation, tokens map directly to user IDs with roles stored in the database.
    Token format: "Bearer <user_id>" for simplicity in testing.
    """
    
    def __init__(self, db_connection):
        self.db = db_connection
    
    def get_current_user(self, credentials: Optional[HTTPAuthorizationCredentials]) -> Dict[str, Any]:
        """
        PUBLIC_INTERFACE
        Extract and validate user from Bearer token.
        
        Args:
            credentials: HTTP authorization credentials
            
        Returns:
            Dict with user_id and role
            
        Raises:
            HTTPException: If authentication fails
        """
        if not credentials:
            raise HTTPException(status_code=401, detail="Missing authentication token")
        
        # Extract user_id from token (in this stub, token IS the user_id)
        user_id = credentials.credentials
        
        # Look up user in database
        cursor = self.db.execute(
            "SELECT user_id, role FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        return {
            "user_id": row["user_id"],
            "role": row["role"]
        }
