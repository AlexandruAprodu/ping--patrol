from typing import Annotated

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Response,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from .constants import (
    REFRESH_TOKEN_COOKIE_NAME,
    REFRESH_TOKEN_COOKIE_PATH,
    REFRESH_TOKEN_COOKIE_SAMESITE,
    REFRESH_TOKEN_COOKIE_SECURE,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from .security import get_current_user
from .db import get_db
from .models import User
from .schemas import RegisterRequest, TokenResponse
from .schemas import UserResponse
from .service import AuthService
from .constants import REFRESH_TOKEN


router = APIRouter()


def set_refresh_cookie(
    response: Response,
    refresh_token: str,
) -> None:
    """Set the refresh cookie for the current resource.
    Apply the value consistently to the underlying state.
    """
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=REFRESH_TOKEN_COOKIE_SECURE,
        samesite=REFRESH_TOKEN_COOKIE_SAMESITE,
        path=REFRESH_TOKEN_COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    """Handle the clear refresh cookie operation for this component.
    Return or update the state expected by the surrounding workflow.
    """
    response.delete_cookie(
        key=REFRESH_TOKEN_COOKIE_NAME,
        path=REFRESH_TOKEN_COOKIE_PATH,
        secure=REFRESH_TOKEN_COOKIE_SECURE,
        httponly=True,
        samesite=REFRESH_TOKEN_COOKIE_SAMESITE,
    )


def public_token_payload(token_pair: dict) -> dict:
    """Handle the public token payload operation for this component.
    Return or update the state expected by the surrounding workflow.
    """
    return {
        "access_token": token_pair["access_token"],
        "token_type": token_pair.get("token_type", "bearer"),
    }


@router.post(
    "/register/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_db),
):
    """Handle the register operation for this component.
    Return or update the state expected by the surrounding workflow.
    """
    service = AuthService(session)
    return await service.register(payload)


@router.post(
    "/login",
    response_model=TokenResponse,
)
async def login(
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_db),
):
    """Handle the login operation for this component.
    Return or update the state expected by the surrounding workflow.
    """
    service = AuthService(session)
    token_pair = await service.login(
        identifier=form.username,
        password=form.password,
    )
    set_refresh_cookie(
        response=response,
        refresh_token=token_pair[REFRESH_TOKEN],
    )
    return public_token_payload(token_pair)


@router.post(
    "/refresh/",
    response_model=TokenResponse,
)
async def refresh(
    response: Response,
    refresh_token: Annotated[
        str | None,
        Cookie(alias=REFRESH_TOKEN_COOKIE_NAME),
    ] = None,
    session: AsyncSession = Depends(get_db),
):
    """Handle the refresh operation for this component.
    Return or update the state expected by the surrounding workflow.
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token cookie is missing.",
        )

    service = AuthService(session)
    token_pair = await service.refresh(refresh_token)

    set_refresh_cookie(
        response=response,
        refresh_token=token_pair[REFRESH_TOKEN],
    )
    return public_token_payload(token_pair)


@router.post("/logout/")
async def logout(
    response: Response,
    refresh_token: Annotated[
        str | None,
        Cookie(alias=REFRESH_TOKEN_COOKIE_NAME),
    ] = None,
    session: AsyncSession = Depends(get_db),
):
    """Handle the logout operation for this component.
    Return or update the state expected by the surrounding workflow.
    """
    if refresh_token:
        service = AuthService(session)
        await service.logout(refresh_token)

    clear_refresh_cookie(response)

    return {
        "detail": "Logged out.",
    }


@router.get("/me/", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    """Handle the me operation for this component.
    Return or update the state expected by the surrounding workflow.
    """
    return current_user
