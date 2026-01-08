"""Authentication API routes."""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from maruntime.auth.service import (
    AuthService,
    InvalidCredentialsError,
    UserExistsError,
)


# Cookie settings
SESSION_COOKIE_NAME = "session_token"
SESSION_COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds


class RegisterRequest(BaseModel):
    login: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=1, max_length=100)
    about: str | None = Field(default=None)


class LoginRequest(BaseModel):
    login: str
    password: str


class ChangePasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=1)


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    about: str | None = None


class UserResponse(BaseModel):
    id: str
    login: str
    display_name: str
    about: str | None
    created_at: str

    class Config:
        from_attributes = True


def create_auth_router(
    session_factory: Callable[[], AsyncSession],
) -> APIRouter:
    """Create authentication router with database session factory.
    
    Args:
        session_factory: Async function that returns database session
        
    Returns:
        FastAPI APIRouter with auth endpoints
    """
    router = APIRouter(prefix="/auth", tags=["auth"])

    async def get_db() -> AsyncSession:
        async with session_factory() as session:
            yield session

    @router.post("/register", response_model=UserResponse)
    async def register(
        request: RegisterRequest,
        response: Response,
        db: AsyncSession = Depends(get_db),
    ) -> UserResponse:
        """Register a new user account."""
        auth_service = AuthService(db)
        
        try:
            user = await auth_service.register(
                login=request.login,
                password=request.password,
                display_name=request.display_name,
                about=request.about,
            )
        except UserExistsError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Auto-login after registration
        _, token = await auth_service.login(request.login, request.password)
        
        # Set session cookie
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            max_age=SESSION_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
        )

        return UserResponse(
            id=user.id,
            login=user.login,
            display_name=user.display_name,
            about=user.about,
            created_at=user.created_at.isoformat(),
        )

    @router.post("/login", response_model=UserResponse)
    async def login(
        request: LoginRequest,
        response: Response,
        db: AsyncSession = Depends(get_db),
    ) -> UserResponse:
        """Login with credentials and receive session cookie."""
        auth_service = AuthService(db)
        
        try:
            user, token = await auth_service.login(request.login, request.password)
        except InvalidCredentialsError as e:
            raise HTTPException(status_code=401, detail=str(e))

        # Set session cookie
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            max_age=SESSION_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
        )

        return UserResponse(
            id=user.id,
            login=user.login,
            display_name=user.display_name,
            about=user.about,
            created_at=user.created_at.isoformat(),
        )

    @router.post("/logout")
    async def logout(
        request: Request,
        response: Response,
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        """Logout and invalidate session."""
        token = request.cookies.get(SESSION_COOKIE_NAME)
        
        if token:
            auth_service = AuthService(db)
            await auth_service.logout(token)

        # Clear cookie
        response.delete_cookie(key=SESSION_COOKIE_NAME)
        
        return {"message": "Logged out successfully"}

    @router.get("/me", response_model=UserResponse)
    async def get_current_user(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> UserResponse:
        """Get current authenticated user."""
        token = request.cookies.get(SESSION_COOKIE_NAME)
        
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")

        auth_service = AuthService(db)
        user = await auth_service.validate_session(token)
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired session")

        return UserResponse(
            id=user.id,
            login=user.login,
            display_name=user.display_name,
            about=user.about,
            created_at=user.created_at.isoformat(),
        )

    @router.put("/password")
    async def change_password(
        request_body: ChangePasswordRequest,
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        """Change password for current user."""
        token = request.cookies.get(SESSION_COOKIE_NAME)
        
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")

        auth_service = AuthService(db)
        user = await auth_service.validate_session(token)
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired session")

        await auth_service.change_password(user.id, request_body.new_password)
        
        return {"message": "Password changed successfully"}

    @router.put("/profile", response_model=UserResponse)
    async def update_profile(
        request_body: UpdateProfileRequest,
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> UserResponse:
        """Update current user profile."""
        token = request.cookies.get(SESSION_COOKIE_NAME)
        
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")

        auth_service = AuthService(db)
        user = await auth_service.validate_session(token)
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired session")

        updated_user = await auth_service.update_user(
            user_id=user.id,
            display_name=request_body.display_name,
            about=request_body.about,
        )
        
        if not updated_user:
            raise HTTPException(status_code=404, detail="User not found")

        return UserResponse(
            id=updated_user.id,
            login=updated_user.login,
            display_name=updated_user.display_name,
            about=updated_user.about,
            created_at=updated_user.created_at.isoformat(),
        )

    return router


__all__ = ["create_auth_router", "SESSION_COOKIE_NAME"]
