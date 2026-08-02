from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_scoped_session, require_permission
from app.modules.users import service
from app.modules.users.schemas import (
    PasswordReset,
    PermissionOut,
    RoleOut,
    UserCreate,
    UserOut,
    UserUpdate,
)

router = APIRouter()


@router.get("/users", response_model=list[UserOut])
async def list_users(
    principal: Principal = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_users(session, principal)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    principal: Principal = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.create_user(session, principal, payload)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.put("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    principal: Principal = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.update_user(session, principal, user_id, payload)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.post("/users/{user_id}/password", response_model=UserOut)
async def reset_password(
    user_id: int,
    payload: PasswordReset,
    principal: Principal = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.reset_password(session, principal, user_id, payload.password)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    principal: Principal = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_roles(session, principal)


@router.get("/permissions", response_model=list[PermissionOut])
async def list_permissions(
    principal: Principal = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_permissions(session, principal)
