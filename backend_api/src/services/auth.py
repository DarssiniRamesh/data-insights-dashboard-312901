"""
PUBLIC_INTERFACE
Authentication and authorization service with local token-based auth and RBAC.
"""
import hashlib
import hmac
import base64
import json
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


security = HTTPBearer(auto_error=False)

# Secret key for HMAC token signing (should be in env for production)
SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "dev-secret-key-change-in-production-12345")
TOKEN_EXPIRY_MINUTES = int(os.getenv("TOKEN_EXPIRY_MINUTES", "60"))

# Valid RBAC roles
VALID_ROLES = ["submitter", "reviewer", "approver", "auditor", "admin"]

# Legacy role mapping for backward compatibility
LEGACY_ROLE_MAP = {
    "publisher": "submitter",
    "steward": "approver",
    "governance_admin": "admin",
    "auditor": "auditor",
    "system": "admin"
}


class AuthService:
    """
    Authentication and authorization service.
    
    Provides:
    - Password hashing with PBKDF2
    - JWT-like token generation and validation with HMAC
    - User CRUD operations
    - Role-based access control
    - Segregation of Duties (SoD) enforcement
    """
    
    def __init__(self, db_connection):
        self.db = db_connection
    
    # PUBLIC_INTERFACE
    def hash_password(self, password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
        """
        Hash a password using PBKDF2-HMAC-SHA256.
        
        Args:
            password: Plain text password
            salt: Optional salt (generated if not provided)
            
        Returns:
            Tuple of (hash_hex, salt_hex)
        """
        if salt is None:
            salt = os.urandom(32)
        
        iterations = 100000
        pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
        
        return pwd_hash.hex(), salt.hex()
    
    # PUBLIC_INTERFACE
    def verify_password(self, password: str, stored_hash: str, stored_salt: str) -> bool:
        """
        Verify a password against stored hash and salt.
        
        Args:
            password: Plain text password to verify
            stored_hash: Stored password hash (hex)
            stored_salt: Stored salt (hex)
            
        Returns:
            True if password matches, False otherwise
        """
        computed_hash, _ = self.hash_password(password, bytes.fromhex(stored_salt))
        return hmac.compare_digest(computed_hash, stored_hash)
    
    # PUBLIC_INTERFACE
    def create_token(self, user_id: str, username: str, roles: List[str]) -> Dict[str, Any]:
        """
        Create a signed bearer token.
        
        Token format: base64(payload).base64(hmac_signature)
        Payload: {"user_id": "...", "username": "...", "roles": [...], "iat": ..., "exp": ...}
        
        Args:
            user_id: User identifier
            username: Username
            roles: List of user roles
            
        Returns:
            Dict with access_token, token_type, expires_in
        """
        now = datetime.utcnow()
        exp = now + timedelta(minutes=TOKEN_EXPIRY_MINUTES)
        
        payload = {
            "user_id": user_id,
            "username": username,
            "roles": roles,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp())
        }
        
        # Encode payload
        payload_json = json.dumps(payload, separators=(',', ':'))
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode('utf-8')).decode('utf-8').rstrip('=')
        
        # Create HMAC signature
        message = payload_b64.encode('utf-8')
        signature = hmac.new(SECRET_KEY.encode('utf-8'), message, hashlib.sha256).digest()
        signature_b64 = base64.urlsafe_b64encode(signature).decode('utf-8').rstrip('=')
        
        # Combine into token
        token = f"{payload_b64}.{signature_b64}"
        
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": TOKEN_EXPIRY_MINUTES * 60
        }
    
    # PUBLIC_INTERFACE
    def decode_token(self, token: str) -> Dict[str, Any]:
        """
        Decode and validate a bearer token.
        
        Args:
            token: Bearer token string
            
        Returns:
            Decoded payload
            
        Raises:
            ValueError: If token is invalid or expired
        """
        try:
            parts = token.split('.')
            if len(parts) != 2:
                raise ValueError("Invalid token format")
            
            payload_b64, signature_b64 = parts
            
            # Verify signature
            message = payload_b64.encode('utf-8')
            expected_signature = hmac.new(SECRET_KEY.encode('utf-8'), message, hashlib.sha256).digest()
            expected_signature_b64 = base64.urlsafe_b64encode(expected_signature).decode('utf-8').rstrip('=')
            
            if not hmac.compare_digest(signature_b64, expected_signature_b64):
                raise ValueError("Invalid token signature")
            
            # Decode payload
            padding = '=' * (4 - len(payload_b64) % 4)
            payload_json = base64.urlsafe_b64decode(payload_b64 + padding).decode('utf-8')
            payload = json.loads(payload_json)
            
            # Check expiration
            now = int(datetime.utcnow().timestamp())
            if payload.get('exp', 0) < now:
                raise ValueError("Token expired")
            
            return payload
        
        except Exception as e:
            raise ValueError(f"Token validation failed: {str(e)}")
    
    # PUBLIC_INTERFACE
    def get_current_user(self, credentials: Optional[HTTPAuthorizationCredentials]) -> Dict[str, Any]:
        """
        Extract and validate user from Bearer token.
        
        Args:
            credentials: HTTP authorization credentials
            
        Returns:
            Dict with user_id, username, roles, and legacy role field
            
        Raises:
            HTTPException: If authentication fails
        """
        if not credentials:
            raise HTTPException(status_code=401, detail="Missing authentication token")
        
        try:
            # Decode and validate token
            payload = self.decode_token(credentials.credentials)
            
            # Verify user still exists and is active
            cursor = self.db.execute(
                "SELECT user_id, username, roles, is_active FROM users WHERE user_id = ?",
                (payload["user_id"],)
            )
            row = cursor.fetchone()
            
            if not row:
                raise HTTPException(status_code=401, detail="Invalid or expired token")
            
            if not row["is_active"]:
                raise HTTPException(status_code=401, detail="User account is inactive")
            
            roles = row["roles"].split(',') if row["roles"] else []
            
            # For backward compatibility, provide a single 'role' field
            # Use first role or map back to legacy role
            primary_role = roles[0] if roles else "submitter"
            
            return {
                "user_id": row["user_id"],
                "username": row["username"],
                "roles": roles,
                "role": primary_role  # For backward compatibility
            }
        
        except ValueError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=401, detail="Authentication failed")
    
    # PUBLIC_INTERFACE
    def create_user(self, username: str, password: str, roles: List[str]) -> Dict[str, Any]:
        """
        Create a new user.
        
        Args:
            username: Username (must be unique)
            password: Plain text password
            roles: List of roles to assign
            
        Returns:
            Dict with user_id, username, roles, created_at
            
        Raises:
            ValueError: If username exists or roles invalid
        """
        # Validate roles
        for role in roles:
            if role not in VALID_ROLES:
                raise ValueError(f"Invalid role: {role}. Must be one of {VALID_ROLES}")
        
        # Check if username exists
        cursor = self.db.execute("SELECT user_id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            raise ValueError(f"Username '{username}' already exists")
        
        # Hash password
        pwd_hash, salt = self.hash_password(password)
        
        # Generate user ID
        import uuid
        user_id = f"u-{str(uuid.uuid4())[:8]}"
        created_at = datetime.utcnow().isoformat() + "Z"
        
        # Store user
        roles_str = ','.join(roles)
        self.db.execute(
            """INSERT INTO users (user_id, username, password_hash, password_salt, roles, is_active, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, username, pwd_hash, salt, roles_str, True, created_at)
        )
        self.db.commit()
        
        return {
            "user_id": user_id,
            "username": username,
            "roles": roles,
            "created_at": created_at
        }
    
    # PUBLIC_INTERFACE
    def authenticate_user(self, username: str, password: str) -> Dict[str, Any]:
        """
        Authenticate a user with username and password.
        
        Args:
            username: Username
            password: Plain text password
            
        Returns:
            Token response with access_token, token_type, expires_in
            
        Raises:
            HTTPException: If authentication fails
        """
        cursor = self.db.execute(
            "SELECT user_id, username, password_hash, password_salt, roles, is_active FROM users WHERE username = ?",
            (username,)
        )
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        if not row["is_active"]:
            raise HTTPException(status_code=401, detail="User account is inactive")
        
        # Verify password
        if not self.verify_password(password, row["password_hash"], row["password_salt"]):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        # Generate token
        roles = row["roles"].split(',') if row["roles"] else []
        return self.create_token(row["user_id"], row["username"], roles)
    
    # PUBLIC_INTERFACE
    def assign_role(self, user_id: str, role: str, assigner_roles: List[str]) -> Dict[str, Any]:
        """
        Assign an additional role to a user.
        
        Args:
            user_id: User to assign role to
            role: Role to assign
            assigner_roles: Roles of the user making the assignment
            
        Returns:
            Updated user info
            
        Raises:
            HTTPException: If unauthorized or invalid
        """
        # Only admin or auditor can assign roles
        if "admin" not in assigner_roles and "auditor" not in assigner_roles:
            raise HTTPException(status_code=403, detail="Only admin or auditor can assign roles")
        
        # Validate role
        if role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Invalid role: {role}. Must be one of {VALID_ROLES}")
        
        # Get current user
        cursor = self.db.execute("SELECT user_id, username, roles FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        
        # Parse current roles
        current_roles = row["roles"].split(',') if row["roles"] else []
        
        # Add role if not already present
        if role not in current_roles:
            current_roles.append(role)
            roles_str = ','.join(current_roles)
            
            self.db.execute("UPDATE users SET roles = ? WHERE user_id = ?", (roles_str, user_id))
            self.db.commit()
        
        return {
            "user_id": row["user_id"],
            "username": row["username"],
            "roles": current_roles
        }
    
    # PUBLIC_INTERFACE
    def check_roles(self, user_roles: List[str], required_roles: List[str]) -> bool:
        """
        Check if user has any of the required roles.
        
        Args:
            user_roles: User's roles
            required_roles: Required roles (user needs at least one)
            
        Returns:
            True if user has at least one required role
        """
        return any(role in user_roles for role in required_roles)
    
    # PUBLIC_INTERFACE
    def enforce_sod(self, submission_id: str, approver_user_id: str) -> None:
        """
        Enforce Segregation of Duties: approver cannot be the same as submitter.
        
        Args:
            submission_id: Submission being approved
            approver_user_id: User attempting to approve
            
        Raises:
            HTTPException: If SoD is violated
        """
        cursor = self.db.execute(
            "SELECT submitter_user_id FROM submissions WHERE submission_id = ?",
            (submission_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Submission not found")
        
        if row["submitter_user_id"] == approver_user_id:
            raise HTTPException(
                status_code=403,
                detail="Segregation of Duties violation: submitter cannot approve their own submission"
            )


# Dependency functions for FastAPI

# PUBLIC_INTERFACE
def get_current_user_dep(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    FastAPI dependency to get current authenticated user.
    
    Returns:
        User dict with user_id, username, roles, role
    """
    from src.database import get_connection
    db = get_connection()
    auth_service = AuthService(db)
    return auth_service.get_current_user(credentials)


# PUBLIC_INTERFACE
def require_roles(required_roles: List[str]):
    """
    Create a FastAPI dependency that enforces role requirements.
    
    Args:
        required_roles: List of roles (user needs at least one)
        
    Returns:
        Dependency function
    """
    def role_checker(user: Dict[str, Any] = Security(get_current_user_dep)):
        user_roles = user.get("roles", [])
        if not any(role in user_roles for role in required_roles):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required roles: {required_roles}"
            )
        return user
    
    return role_checker
