"""v2 §9 print endpoints.

The server assembles the whole document; the browser lays it out for a 58mm
till roll, an 80mm roll, A5 or A4. Nothing is rendered here — but every figure
comes from the posted document, so what prints cannot drift from what posted.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_principal, get_scoped_session, require_permission
from app.services import printing

router = APIRouter()

READ_PERM = {
    "sales_bill": "sales.read",
    "sales_return": "sales.read",
    "purchase_bill": "purchase.read",
    "purchase_return": "purchase.read",
}


class PrintSettingsIn(BaseModel):
    default_format: str | None = Field(default=None, pattern="^(a4|a5|thermal80|thermal58)$")
    show_hsn: bool | None = None
    show_tax_summary: bool | None = None
    show_amount_in_words: bool | None = None
    show_bank_details: bool | None = None
    footer_text: str | None = None
    terms: str | None = None


@router.get("/print/settings")
async def get_print_settings(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    return await printing.print_settings(session, principal.org_id)


@router.put("/print/settings")
async def set_print_settings(
    payload: PrintSettingsIn,
    principal: Principal = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Stored as system_setting rows under the print.* prefix."""
    import json

    from sqlalchemy import text

    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        await session.execute(
            text("INSERT INTO system_setting (org_id, key, value) "
                 "VALUES (:o, :k, CAST(:v AS jsonb)) "
                 "ON CONFLICT (org_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"),
            {"o": principal.org_id, "k": f"print.{key}", "v": json.dumps({"value": value})},
        )
    return await printing.print_settings(session, principal.org_id)


@router.get("/print/{doc_type}/{doc_id}")
async def print_document(
    doc_type: str,
    doc_id: int,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Everything needed to render this document on paper or a till roll."""
    perm = READ_PERM.get(doc_type)
    if perm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"'{doc_type}' cannot be printed")
    if not principal.has(perm):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {perm}")
    try:
        return await printing.build_document(session, principal, doc_type, doc_id)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
