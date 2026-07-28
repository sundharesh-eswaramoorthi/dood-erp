from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.models.product import UnitOfMeasure
from app.modules.units.schemas import UnitCreate


async def list_units(session: AsyncSession, principal: Principal) -> list[UnitOfMeasure]:
    stmt = select(UnitOfMeasure).order_by(UnitOfMeasure.code)
    return list((await session.execute(stmt)).scalars().all())


async def create_unit(
    session: AsyncSession, principal: Principal, data: UnitCreate
) -> UnitOfMeasure:
    unit = UnitOfMeasure(org_id=principal.org_id, code=data.code.upper(), name=data.name)
    session.add(unit)
    try:
        await session.flush()
    except IntegrityError as e:
        raise ValueError(f"Unit code '{data.code}' already exists") from e
    return unit
