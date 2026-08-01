from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_principal, get_scoped_session, require_permission
from app.modules.settings.schemas import (
    BranchCreate,
    BranchOut,
    BranchUpdate,
    DocumentTypeCreate,
    DocumentTypeOut,
    DocumentTypeUpdate,
    GodownCreate,
    GodownOut,
    GodownUpdate,
    SettingOut,
    SettingUpsert,
    TagCreate,
    TagOut,
    TaxRateCreate,
    TaxRateOut,
)
from app.modules.settings import service

router = APIRouter()


def _admin():
    return require_permission("settings.manage")


# ---- branches (v2 §9 "Add branch") ----
@router.get("/branches", response_model=list[BranchOut])
async def branches_list(
    include_inactive: bool = False,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_branches(session, principal, include_inactive)


@router.post("/branches", response_model=BranchOut, status_code=status.HTTP_201_CREATED)
async def branches_create(
    payload: BranchCreate,
    principal: Principal = Depends(_admin()),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.create_branch(session, principal, payload)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.put("/branches/{branch_id}", response_model=BranchOut)
async def branches_update(
    branch_id: int,
    payload: BranchUpdate,
    principal: Principal = Depends(_admin()),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.update_branch(session, principal, branch_id, payload)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Branch not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


# ---- godowns (v2 §2 "Godown management") ----
@router.get("/godowns", response_model=list[GodownOut])
async def godowns_list(
    include_inactive: bool = False,
    all_branches: bool = False,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_godowns(session, principal, include_inactive, all_branches)


@router.post("/godowns", response_model=GodownOut, status_code=status.HTTP_201_CREATED)
async def godowns_create(
    payload: GodownCreate,
    principal: Principal = Depends(_admin()),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.create_godown(session, principal, payload)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Branch not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.put("/godowns/{godown_id}", response_model=GodownOut)
async def godowns_update(
    godown_id: int,
    payload: GodownUpdate,
    principal: Principal = Depends(_admin()),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.update_godown(session, principal, godown_id, payload)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Godown not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))


# ---- document types (v2 §9 "Add documents (customisable)") ----
@router.get("/document-types", response_model=list[DocumentTypeOut])
async def doctypes_list(
    applies_to: str | None = None,
    include_inactive: bool = False,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await service.list_document_types(session, principal, applies_to, include_inactive)


@router.post("/document-types", response_model=DocumentTypeOut, status_code=status.HTTP_201_CREATED)
async def doctypes_create(
    payload: DocumentTypeCreate,
    principal: Principal = Depends(_admin()),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.create_document_type(session, principal, payload)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.put("/document-types/{doc_type_id}", response_model=DocumentTypeOut)
async def doctypes_update(
    doc_type_id: int,
    payload: DocumentTypeUpdate,
    principal: Principal = Depends(_admin()),
    session: AsyncSession = Depends(get_scoped_session),
):
    try:
        return await service.update_document_type(session, principal, doc_type_id, payload)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document type not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


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
