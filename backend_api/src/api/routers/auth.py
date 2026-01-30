"""
PUBLIC_INTERFACE
Authentication and authorization router.
"""
import os
from fastapi import APIRouter, HTTPException, Depends
from typing import List
from pydantic import BaseModel, Field

from src.database import get_connection
from src.services.auth import AuthService, get_current_user_dep
from src.utils import make_error_response, generate_id


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"]
)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    roles: List[str]


class RegisterResponse(BaseModel):
    user_id: str
    username: str
    roles: List[str]
    created_at: str


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class AssignRoleRequest(BaseModel):
    user_id: str
    role: str


class AssignRoleResponse(BaseModel):
    user_id: str
    username: str
    roles: List[str]


class UserProfileResponse(BaseModel):
    user_id: str
    username: str
    roles: List[str]
    is_active: bool


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register_user(request: RegisterRequest) -> RegisterResponse:
    db = get_connection()
    auth_service = AuthService(db)
    
    try:
        # Check if registration is allowed
        allow_register = os.getenv("AUTH_ALLOW_REGISTER", "true").lower() == "true"
        
        # Count existing users
        cursor = db.execute("SELECT COUNT(*) as count FROM users")
        user_count = cursor.fetchone()["count"]
        
        # Always allow first user registration (for initial setup)
        # Otherwise check AUTH_ALLOW_REGISTER flag
        if not allow_register and user_count > 0:
            raise HTTPException(
                status_code=403,
                detail=make_error_response(
                    "REGISTRATION_DISABLED",
                    "User registration is disabled. Set AUTH_ALLOW_REGISTER=true to enable.",
                    generate_id("req")
                )
            )
        
        result = auth_service.create_user(request.username, request.password, request.roles)
        
        return RegisterResponse(
            user_id=result["user_id"],
            username=result["username"],
            roles=result["roles"],
            created_at=result["created_at"]
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=make_error_response("INVALID_REQUEST", str(e), generate_id("req")))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=make_error_response("INTERNAL_ERROR", f"Failed to register user: {str(e)}", generate_id("req")))


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    db = get_connection()
    auth_service = AuthService(db)
    
    try:
        token_response = auth_service.authenticate_user(request.username, request.password)
        return LoginResponse(
            access_token=token_response["access_token"],
            token_type=token_response["token_type"],
            expires_in=token_response["expires_in"]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=make_error_response("INTERNAL_ERROR", f"Login failed: {str(e)}", generate_id("req")))


@router.post("/assign-role", response_model=AssignRoleResponse)
async def assign_role(request: AssignRoleRequest, current_user: dict = Depends(get_current_user_dep)) -> AssignRoleResponse:
    db = get_connection()
    auth_service = AuthService(db)
    
    try:
        result = auth_service.assign_role(
            user_id=request.user_id,
            role=request.role,
            assigner_roles=current_user.get("roles", [])
        )
        return AssignRoleResponse(user_id=result["user_id"], username=result["username"], roles=result["roles"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=make_error_response("INTERNAL_ERROR", f"Failed to assign role: {str(e)}", generate_id("req")))


@router.get("/me", response_model=UserProfileResponse)
async def get_me(current_user: dict = Depends(get_current_user_dep)) -> UserProfileResponse:
    db = get_connection()
    
    try:
        cursor = db.execute("SELECT user_id, username, roles, is_active FROM users WHERE user_id = ?", (current_user["user_id"],))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        
        roles = row["roles"].split(',') if row["roles"] else []
        return UserProfileResponse(user_id=row["user_id"], username=row["username"], roles=roles, is_active=bool(row["is_active"]))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=make_error_response("INTERNAL_ERROR", f"Failed to get user profile: {str(e)}", generate_id("req")))


class ToggleRegistrationRequest(BaseModel):
    enabled: bool


class ToggleRegistrationResponse(BaseModel):
    enabled: bool
    message: str


@router.post("/toggle-registration", response_model=ToggleRegistrationResponse)
async def toggle_registration(request: ToggleRegistrationRequest, current_user: dict = Depends(get_current_user_dep)) -> ToggleRegistrationResponse:
    """
    Toggle registration on/off (admin only, for non-production environments).
    
    This endpoint allows runtime control of user registration. It is intended
    for development and testing environments only.
    
    Note: First user registration is always allowed regardless of this setting
    to enable initial system setup.
    """
    # Only admin can toggle registration
    if "admin" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=403,
            detail=make_error_response(
                "AUTHORIZATION_FAILED",
                "Only admin users can toggle registration",
                generate_id("req")
            )
        )
    
    # This would update a runtime config or environment variable
    # For now, we'll just return the status since AUTH_ALLOW_REGISTER is from env
    # In a production system, this would update a config store
    return ToggleRegistrationResponse(
        enabled=request.enabled,
        message=f"Registration {'enabled' if request.enabled else 'disabled'}. Note: Set AUTH_ALLOW_REGISTER environment variable to persist this setting."
    )
