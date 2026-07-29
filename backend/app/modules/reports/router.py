from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_scoped_session, require_permission
from app.modules.reports import service

router = APIRouter()


@router.get("/{report}")
async def run_report(
    report: str,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    principal: Principal = Depends(require_permission("reports.view")),
    session: AsyncSession = Depends(get_scoped_session),
):
    fn = service.REPORTS.get(report)
    if fn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown report '{report}'")
    today = dt.date.today()
    dfrom = date_from or today.replace(day=1)
    dto = date_to or today
    return await fn(session, principal, dfrom, dto)
