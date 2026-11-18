import datetime

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from .constants import REFRESH_TOKEN_EXPIRE_DAYS
from .password import hash_password, verify_password
from .security import (
    create_access_token,
    create_refresh_token,
    hash_token,
)
from .models import UserToken
from .models import User
from .schemas import RegisterRequest
from .constants import ACCESS_TOKEN, REFRESH_TOKEN




class AuthService:
    """Coordinates auth business operations.
    Keeps domain logic separate from transport and persistence code.
    """
    def __init__(self, session: AsyncSession):
        """Initialize the AuthService instance with its required dependencies.
        Stores the collaborators and configuration used by later operations.
        """
        self.session = session

    async def register(self, payload: RegisterRequest) -> User:
        """Handle the register operation for this component.
        Return or update the state expected by the surrounding workflow.
        """
        await self._validate_unique_email(payload.email)
        await self._validate_unique_username(payload.username)

        user = User(
            email=payload.email,
            username=payload.username,
            password_hash=await run_in_threadpool(hash_password, payload.password),
        )

        self.session.add(user)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HTTPException(status_code=409, detail="Email or username already exists.") from exc
        await self.session.refresh(user)


        return user

    async def login(self, identifier: str, password: str) -> dict:
        """Handle the login operation for this component.
        Return or update the state expected by the surrounding workflow.
        """
        user = await self._get_user_by_identifier(identifier)

        if user is None:
            self._raise_invalid_credentials()

        if not await run_in_threadpool(verify_password, password, user.password_hash):
            self._raise_invalid_credentials()

        token_pair = await self._create_token_pair(user)


        return token_pair

    async def refresh(self, refresh_token: str) -> dict:
        """Handle the refresh operation for this component.
        Return or update the state expected by the surrounding workflow.
        """
        token_hash = hash_token(refresh_token)

        result = await self.session.execute(
            select(UserToken)
            .where(
                UserToken.refresh_token_hash == token_hash,
            )
            .with_for_update()
        )

        user_token = result.scalars().first()

        if user_token is None:
            self._raise_invalid_refresh_token()

        now = datetime.datetime.now(datetime.UTC)

        if user_token.revoked_at is not None:
            self._raise_invalid_refresh_token()

        if user_token.expires_at <= now:
            self._raise_invalid_refresh_token()

        user_token.revoked_at = now

        user = await self.session.get(User, user_token.user_id)

        if user is None:
            self._raise_invalid_refresh_token()

        token_pair = await self._create_token_pair(
            user,
            commit=False,
        )

        await self.session.commit()


        return token_pair

    async def logout(self, refresh_token: str) -> None:
        """Handle the logout operation for this component.
        Return or update the state expected by the surrounding workflow.
        """
        token_hash = hash_token(refresh_token)

        result = await self.session.execute(
            select(UserToken)
            .where(
                UserToken.refresh_token_hash == token_hash,
            )
            .with_for_update()
        )

        user_token = result.scalars().first()

        if user_token is None:
            await self.session.rollback()
            return

        user_token.revoked_at = datetime.datetime.now(datetime.UTC)

        await self.session.commit()


    async def _create_token_pair(
        self,
        user: User,
        *,
        commit: bool = True,
    ) -> dict:
        """Create a new token pair from the supplied input.
        Persist or prepare the resource and return its current state.
        """
        access_token = create_access_token(user.id)
        refresh_token = create_refresh_token()

        expires_at = datetime.datetime.now(
            datetime.UTC
        ) + datetime.timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

        self.session.add(
            UserToken(
                user_id=user.id,
                refresh_token_hash=hash_token(refresh_token),
                expires_at=expires_at,
            )
        )

        if commit:
            await self.session.commit()
        else:
            await self.session.flush()

        return {
            ACCESS_TOKEN: access_token,
            REFRESH_TOKEN: refresh_token,
            "token_type": "bearer",
        }

    async def _get_user_by_email(self, email: str) -> User | None:
        """Return the user by email needed by the current operation.
        Resolve it from the configured state or backing dependency.
        """
        result = await self.session.execute(
            select(User).where(User.email == email)
        )

        return result.scalars().first()

    async def _validate_unique_email(self, email: str) -> None:
        """Validate the supplied unique email against the expected rules.
        Raise a clear error when the input cannot be accepted.
        """
        user = await self._get_user_by_email(email)

        if user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already exists.",
            )

    async def _validate_unique_username(self, username: str) -> None:
        """Validate the supplied unique username against the expected rules.
        Raise a clear error when the input cannot be accepted.
        """
        result = await self.session.execute(
            select(User).where(User.username == username)
        )

        user = result.scalars().first()

        if user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists.",
            )

    async def _get_user_by_identifier(
        self,
        identifier: str,
    ) -> User | None:
        """Return the user by identifier needed by the current operation.
        Resolve it from the configured state or backing dependency.
        """
        result = await self.session.execute(
            select(User).where(
                or_(
                    User.email == identifier,
                    User.username == identifier,
                )
            )
        )

        return result.scalars().first()

    @staticmethod
    def _raise_invalid_credentials() -> None:
        """Handle the raise invalid credentials operation for this component.
        Return or update the state expected by the surrounding workflow.
        """
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    @staticmethod
    def _raise_invalid_refresh_token() -> None:
        """Handle the raise invalid refresh token operation for this component.
        Return or update the state expected by the surrounding workflow.
        """
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        )
