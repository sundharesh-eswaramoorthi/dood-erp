from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_principal, get_scoped_session, require_permission
from app.modules.settings.schemas import (
    SettingOut,
    SettingUpsert,
    TagCreate,
    TagOut,
    TaxRateCreate,
    TaxRateOut,
)
from app.modules.settings import service

router = APIRouter()


# ---- tax rates ----
@router.get("/tax-rates", response_model=list[TaxRateOut])
async def tax_rates_list(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_tax_rates(session, principal)


@router.post("/tax-rates", response_model=TaxRateOut, status_code=status.HTTP_201_CREATED)
async def tax_rates_create(
    payload: TaxRateCreate,
    principal: Principal = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.create_tax_rate(session, principal, payload)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


# ---- tags ----
@router.get("/tags", response_model=list[TagOut])
async def tags_list(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_tags(session, principal)


@router.post("/tags", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def tags_create(
    payload: TagCreate,
    principal: Principal = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.create_tag(session, principal, payload)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


# ---- system settings / feature flags ----
@router.get("/settings", response_model=list[SettingOut])
async def settings_list(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_settings(session, principal)


@router.put("/settings/{key}", response_model=SettingOut)
async def settings_upsert(
    key: str,
    payload: SettingUpsert,
    principal: Principal = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.upsert_setting(session, principal, key, payload.value)


@router.get("/feature-flags")
async def feature_flags(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.feature_flags(session, principal)
