"""
PUBLIC_INTERFACE
Authentication and authorization router.
"""
import os
from fastapi import APIRouter, HTTPException, Depends, Response, status
from typing import List
from pydantic import BaseModel, Field

from database import get_connection
from services.auth import (
    AuthService,
    get_current_user_dep,
    is_registration_enabled,
    set_registration_enabled,
)
from utils import make_error_response, generate_id


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# PUBLIC_INTERFACE
@router.options(
    "/register",
    include_in_schema=False,
)
async def register_preflight() -> Response:
    """
    PUBLIC_INTERFACE
    CORSPreflightAuthRegisterFlow: respond to browser preflight for user registration.

    Contract:
      - Inputs: An HTTP OPTIONS request (may or may not include CORS preflight headers).
      - Outputs: 204 No Content with an empty body.
      - Errors: None (always succeeds).
      - Side effects: None.

    Notes:
      - Starlette's CORSMiddleware only treats an OPTIONS as a CORS preflight when
        `Access-Control-Request-Method` is present. Some environments/proxies/tools
        may omit it, causing the request to fall through to routing (often resulting
        in 405/400). This explicit handler guarantees a success response for the
        register preflight path.
      - CORSMiddleware (configured at the app level) is still responsible for adding
        the correct `Access-Control-*` headers based on Origin and configured
        allowed origins/credentials.
    """
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# PUBLIC_INTERFACE
@router.options(
    "/login",
    include_in_schema=False,
)
async def login_preflight() -> Response:
    """
    PUBLIC_INTERFACE
    CORSPreflightAuthLoginFlow: respond to browser preflight for login.

    See register_preflight() for rationale. This ensures OPTIONS /api/v1/auth/login
    never falls through to other handlers and returns an error when proxies alter
    the preflight headers.
    """
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# PUBLIC_INTERFACE
@router.options(
    "/{path:path}",
    include_in_schema=False,
)
async def auth_catchall_preflight(path: str) -> Response:
    """
    PUBLIC_INTERFACE
    CORSPreflightAuthCatchAllFlow: respond to any auth preflight OPTIONS.

    Why:
      - Some deployments issue OPTIONS requests for additional auth endpoints
        (e.g., /me, /assign-role, /toggle-registration), or proxies may strip
        the `Access-Control-Request-Method` header causing CORSMiddleware to not
        recognize the request as a preflight.
      - Returning 204 here ensures preflight succeeds consistently for any path
        under the auth router.

    Notes:
      - CORSMiddleware will still be responsible for adding the actual
        Access-Control-* headers when the request includes an Origin and it matches
        configured CORS_ALLOW_ORIGINS.
    """
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    """
    PUBLIC_INTERFACE
    Register a user.

    Registration is enabled by default. It can be toggled at runtime via
    /api/v1/auth/toggle-registration (admin only).

    First-user bootstrap is always allowed (even when disabled) to ensure
    initial system setup is possible.
    """
    db = get_connection()
    auth_service = AuthService(db)

    try:
        # Count existing users (bootstrap behavior)
        cursor = db.execute("SELECT COUNT(*) as count FROM users")
        user_count = cursor.fetchone()["count"]

        # Runtime toggle layered over env default
        allow_register = is_registration_enabled(default_env=os.getenv("AUTH_ALLOW_REGISTER", "true"))

        if not allow_register and user_count > 0:
            raise HTTPException(
                status_code=403,
                detail=make_error_response(
                    "REGISTRATION_DISABLED",
                    "User registration is disabled.",
                    generate_id("req"),
                    {"hint": "Enable via /api/v1/auth/toggle-registration (admin) or set AUTH_ALLOW_REGISTER=true"},
                ),
            )

        result = auth_service.create_user(request.username, request.password, request.roles)

        return RegisterResponse(
            user_id=result["user_id"],
            username=result["username"],
            roles=result["roles"],
            created_at=result["created_at"],
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=make_error_response("INVALID_REQUEST", str(e), generate_id("req")))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=make_error_response("INTERNAL_ERROR", f"Failed to register user: {str(e)}", generate_id("req")),
        )


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """
    PUBLIC_INTERFACE
    Login a user and return a bearer token.
    """
    db = get_connection()
    auth_service = AuthService(db)

    try:
        token_response = auth_service.authenticate_user(request.username, request.password)
        return LoginResponse(
            access_token=token_response["access_token"],
            token_type=token_response["token_type"],
            expires_in=token_response["expires_in"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=make_error_response("INTERNAL_ERROR", f"Login failed: {str(e)}", generate_id("req")))


@router.post("/assign-role", response_model=AssignRoleResponse)
async def assign_role(request: AssignRoleRequest, current_user: dict = Depends(get_current_user_dep)) -> AssignRoleResponse:
    """
    PUBLIC_INTERFACE
    Assign an additional role to an existing user (admin/auditor).
    """
    db = get_connection()
    auth_service = AuthService(db)

    try:
        result = auth_service.assign_role(
            user_id=request.user_id,
            role=request.role,
            assigner_roles=current_user.get("roles", []),
        )
        return AssignRoleResponse(user_id=result["user_id"], username=result["username"], roles=result["roles"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=make_error_response("INTERNAL_ERROR", f"Failed to assign role: {str(e)}", generate_id("req")),
        )


@router.get("/me", response_model=UserProfileResponse)
async def get_me(current_user: dict = Depends(get_current_user_dep)) -> UserProfileResponse:
    """
    PUBLIC_INTERFACE
    Return current authenticated user's profile.
    """
    db = get_connection()

    try:
        cursor = db.execute(
            "SELECT user_id, username, roles, is_active FROM users WHERE user_id = ?",
            (current_user["user_id"],),
        )
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        roles = row["roles"].split(",") if row["roles"] else []
        return UserProfileResponse(
            user_id=row["user_id"],
            username=row["username"],
            roles=roles,
            is_active=bool(row["is_active"]),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=make_error_response("INTERNAL_ERROR", f"Failed to get user profile: {str(e)}", generate_id("req")),
        )


class ToggleRegistrationRequest(BaseModel):
    enabled: bool


class ToggleRegistrationResponse(BaseModel):
    enabled: bool
    message: str


@router.post("/toggle-registration", response_model=ToggleRegistrationResponse)
async def toggle_registration(
    request: ToggleRegistrationRequest,
    current_user: dict = Depends(get_current_user_dep),
) -> ToggleRegistrationResponse:
    """
    PUBLIC_INTERFACE
    Toggle registration on/off (admin only).

    This updates a runtime flag. It does not persist across restarts unless
    AUTH_ALLOW_REGISTER is also set.
    """
    if "admin" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=403,
            detail=make_error_response(
                "AUTHORIZATION_FAILED",
                "Only admin users can toggle registration",
                generate_id("req"),
            ),
        )

    set_registration_enabled(request.enabled)

    return ToggleRegistrationResponse(
        enabled=request.enabled,
        message=(
            f"Registration {'enabled' if request.enabled else 'disabled'} (runtime). "
            "Set AUTH_ALLOW_REGISTER to persist default across restarts."
        ),
    )
