"""Authentication service for user management."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from maruntime.core.services.user_memory_service import get_user_memory_service
from maruntime.persistence.models import User, AuthSession


# Session token expiration (7 days)
SESSION_EXPIRATION_DAYS = 7


class AuthError(Exception):
    """Base authentication error."""
    pass


class InvalidCredentialsError(AuthError):
    """Invalid login or password."""
    pass


class UserExistsError(AuthError):
    """User with this login already exists."""
    pass


class SessionExpiredError(AuthError):
    """Session has expired."""
    pass


class AuthService:
    """Service for user authentication and session management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def register(
        self,
        login: str,
        password: str,
        display_name: str,
        about: str | None = None,
    ) -> User:
        """Register a new user.
        
        Args:
            login: Unique username
            password: Plain text password (will be hashed)
            display_name: How to address the user
            about: Free-form description
            
        Returns:
            Created User object
            
        Raises:
            UserExistsError: If login is already taken
        """
        # Check if user exists
        existing = await self.session.execute(
            select(User).where(User.login == login)
        )
        if existing.scalar_one_or_none():
            raise UserExistsError(f"User '{login}' already exists")

        # Hash password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # Create user
        user = User(
            id=str(uuid.uuid4()),
            login=login,
            password_hash=password_hash,
            display_name=display_name,
            about=about,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        
        # Create user.md profile file
        try:
            user_memory = get_user_memory_service()
            user_memory.create_user_profile(
                user_id=user.id,
                login=login,
                display_name=display_name,
                about=about,
            )
        except Exception:
            # Don't fail registration if file creation fails
            pass
        
        return user

    async def login(self, login: str, password: str) -> tuple[User, str]:
        """Authenticate user and create session.
        
        Args:
            login: Username
            password: Plain text password
            
        Returns:
            Tuple of (User, session_token)
            
        Raises:
            InvalidCredentialsError: If login/password is incorrect
        """
        # Find user
        result = await self.session.execute(
            select(User).where(User.login == login)
        )
        user = result.scalar_one_or_none()
        
        if not user or not bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
            raise InvalidCredentialsError("Invalid login or password")

        # Generate session token
        token = secrets.token_urlsafe(32)
        token_hash = self._hash_token(token)

        # Create auth session
        auth_session = AuthSession(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.utcnow() + timedelta(days=SESSION_EXPIRATION_DAYS),
        )
        self.session.add(auth_session)
        await self.session.commit()

        return user, token

    async def logout(self, token: str) -> None:
        """Invalidate session token.
        
        Args:
            token: Session token to invalidate
        """
        token_hash = self._hash_token(token)
        await self.session.execute(
            delete(AuthSession).where(AuthSession.token_hash == token_hash)
        )
        await self.session.commit()

    async def validate_session(self, token: str) -> User | None:
        """Validate session token and return user.
        
        Args:
            token: Session token
            
        Returns:
            User if valid, None otherwise
        """
        token_hash = self._hash_token(token)
        
        result = await self.session.execute(
            select(AuthSession)
            .where(AuthSession.token_hash == token_hash)
            .where(AuthSession.expires_at > datetime.utcnow())
        )
        auth_session = result.scalar_one_or_none()
        
        if not auth_session:
            return None

        # Get user
        result = await self.session.execute(
            select(User).where(User.id == auth_session.user_id)
        )
        return result.scalar_one_or_none()

    async def change_password(self, user_id: str, new_password: str) -> None:
        """Change user password.
        
        Args:
            user_id: User ID
            new_password: New plain text password
        """
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            user.password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            user.updated_at = datetime.utcnow()
            await self.session.commit()

    async def get_user(self, user_id: str) -> User | None:
        """Get user by ID.
        
        Args:
            user_id: User ID
            
        Returns:
            User or None
        """
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def update_user(
        self,
        user_id: str,
        display_name: str | None = None,
        about: str | None = None,
    ) -> User | None:
        """Update user profile.
        
        Args:
            user_id: User ID
            display_name: New display name (optional)
            about: New about text (optional)
            
        Returns:
            Updated user or None if not found
        """
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            if display_name is not None:
                user.display_name = display_name
            if about is not None:
                user.about = about
            user.updated_at = datetime.utcnow()
            await self.session.commit()
            await self.session.refresh(user)
            
            # Update user.md profile file
            try:
                user_memory = get_user_memory_service()
                user_memory.update_user_profile(
                    user_id=user.id,
                    display_name=display_name,
                    about=about,
                )
            except Exception:
                # Don't fail update if file update fails
                pass
            
        return user

    async def cleanup_expired_sessions(self) -> int:
        """Remove expired auth sessions.
        
        Returns:
            Number of sessions removed
        """
        result = await self.session.execute(
            delete(AuthSession).where(AuthSession.expires_at < datetime.utcnow())
        )
        await self.session.commit()
        return result.rowcount

    @staticmethod
    def _hash_token(token: str) -> str:
        """Hash token for storage."""
        return hashlib.sha256(token.encode()).hexdigest()


__all__ = [
    "AuthService",
    "AuthError",
    "InvalidCredentialsError",
    "UserExistsError",
    "SessionExpiredError",
]
