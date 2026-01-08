"""Authentication middleware for FastAPI."""

from __future__ import annotations

from typing import Callable, Optional

from fastapi import Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from maruntime.auth.service import AuthService
from maruntime.auth.routes import SESSION_COOKIE_NAME
from maruntime.persistence.models import User


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware that validates session cookies and adds user to request state.
    
    For each request, checks if there's a valid session cookie and if so,
    attaches the authenticated user to `request.state.user`.
    
    Public endpoints (not requiring auth) can check `request.state.user is None`.
    Protected endpoints should use the `get_current_user` dependency.
    """

    def __init__(
        self,
        app,
        session_factory: Callable[[], AsyncSession],
        exclude_paths: list[str] | None = None,
    ) -> None:
        """Initialize auth middleware.
        
        Args:
            app: FastAPI/Starlette app
            session_factory: Async context manager that yields database session
            exclude_paths: Paths to skip authentication (e.g., /auth/login)
        """
        super().__init__(app)
        self.session_factory = session_factory
        self.exclude_paths = set(exclude_paths or [])

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and validate auth if session cookie present."""
        # Initialize user as None
        request.state.user = None
        request.state.user_id = None

        # Get session token from cookie
        token = request.cookies.get(SESSION_COOKIE_NAME)
        
        if token:
            try:
                async with self.session_factory() as db:
                    auth_service = AuthService(db)
                    user = await auth_service.validate_session(token)
                    
                    if user:
                        request.state.user = user
                        request.state.user_id = user.id
            except Exception:
                # Log error but don't fail request - just treat as unauthenticated
                pass

        response = await call_next(request)
        return response


async def get_current_user(request: Request) -> User:
    """FastAPI dependency that requires authenticated user.
    
    Use as a dependency in route handlers to require authentication:
    
        @app.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            return {"user": user.display_name}
    
    Raises:
        HTTPException: 401 if not authenticated
    """
    if not hasattr(request.state, 'user') or request.state.user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return request.state.user


async def get_optional_user(request: Request) -> Optional[User]:
    """FastAPI dependency that returns user if authenticated, None otherwise.
    
    Use for routes that work both with and without authentication:
    
        @app.get("/maybe-protected")
        async def maybe_protected(user: User | None = Depends(get_optional_user)):
            if user:
                return {"message": f"Hello {user.display_name}"}
            return {"message": "Hello guest"}
    """
    if hasattr(request.state, 'user'):
        return request.state.user
    return None


__all__ = ["AuthMiddleware", "get_current_user", "get_optional_user"]
