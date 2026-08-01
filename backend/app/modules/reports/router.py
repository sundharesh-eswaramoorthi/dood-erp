from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_scoped_session, require_permission
from app.modules.reports import service
from app.modules.reports.service import Filters

router = APIRouter()


@router.get("")
async def list_reports(
    principal: Principal = Depends(require_permission("reports.view")),
):
    """The v2 §6 catalogue, grouped — the UI builds its picker from this rather
    than hard-coding 48 entries."""
    return {"count": len(service.REPORTS), "reports": service.catalogue()}


@router.get("/{report}")
async def run_report(
    report: str,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    branch_id: int | None = None,
    party_id: int | None = None,
    product_id: int | None = None,
    category_id: int | None = None,
    godown_id: int | None = None,
    payment_type_id: int | None = None,
    principal: Principal = Depends(require_permission("reports.view")),
    session: AsyncSession = Depends(get_scoped_session),
):
    entry = service.REPORTS.get(report)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown report '{report}'")
    group, title, fn = entry

    today = dt.date.today()
    filters = Filters(
        date_from=date_from or today.replace(day=1),
        date_to=date_to or today,
        branch_id=branch_id, party_id=party_id, product_id=product_id,
        category_id=category_id, godown_id=godown_id, payment_type_id=payment_type_id,
    )
    result = await fn(session, principal, filters)
    return {
        "key": report, "group": group, "title": title,
        "date_from": filters.date_from, "date_to": filters.date_to,
        **result,
    }
