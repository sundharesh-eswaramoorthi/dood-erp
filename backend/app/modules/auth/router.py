from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import Principal, get_principal
from app.core.security import decode_token
from app.models.user import AppUser
from app.modules.auth.schemas import RefreshRequest, TokenResponse
from app.modules.auth.service import authenticate, build_login

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    user = await authenticate(session, form.username, form.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    return await build_login(session, user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_session)):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("typ") != "refresh":
            raise ValueError("not a refresh token")
        user_id = int(payload["sub"])
    except Exception:  # noqa: BLE001
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    user = (
        await session.execute(select(AppUser).where(AppUser.id == user_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return await build_login(session, user)


@router.get("/me")
async def me(principal: Principal = Depends(get_principal)):
    return {
        "user_id": principal.user_id,
        "org_id": principal.org_id,
        "branch_ids": principal.branch_ids,
        "perms": sorted(principal.perms),
        "name": principal.name,
    }
