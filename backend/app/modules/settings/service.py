from __future__ import annotations

import json

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.models.settings import SystemSetting, TagDefinition, TaxRate
from app.modules.settings.schemas import TagCreate, TaxRateCreate


# ---- branches & godowns (org masters; filtered explicitly) ----
async def list_branches(session: AsyncSession, principal: Principal) -> list[dict]:
    rows = (
        await session.execute(
            text("SELECT id, name FROM branch WHERE org_id = :o AND is_active ORDER BY name"),
            {"o": principal.org_id},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def list_godowns(session: AsyncSession, principal: Principal) -> list[dict]:
    rows = (
        await session.execute(
            text(
                "SELECT id, name, branch_id FROM godown "
                "WHERE org_id = :o AND is_active AND branch_id = ANY(:b) ORDER BY name"
            ),
            {"o": principal.org_id, "b": principal.branch_ids or [-1]},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


# ---- tax rates ----
async def list_tax_rates(session: AsyncSession, principal: Principal) -> list[TaxRate]:
    return list((await session.execute(select(TaxRate).order_by(TaxRate.rate))).scalars().all())


async def create_tax_rate(session: AsyncSession, principal: Principal, data: TaxRateCreate) -> TaxRate:
    row = TaxRate(org_id=principal.org_id, name=data.name, rate=data.rate)
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as e:
        raise ValueError(f"Tax rate '{data.name}' already exists") from e
    return row


# ---- tags ----
async def list_tags(session: AsyncSession, principal: Principal) -> list[TagDefinition]:
    return list(
        (await session.execute(select(TagDefinition).order_by(TagDefinition.name))).scalars().all()
    )


async def create_tag(session: AsyncSession, principal: Principal, data: TagCreate) -> TagDefinition:
    row = TagDefinition(org_id=principal.org_id, name=data.name, color=data.color)
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as e:
        raise ValueError(f"Tag '{data.name}' already exists") from e
    return row


# ---- system settings / feature flags ----
async def list_settings(session: AsyncSession, principal: Principal) -> list[SystemSetting]:
    return list(
        (await session.execute(select(SystemSetting).order_by(SystemSetting.key))).scalars().all()
    )


async def upsert_setting(
    session: AsyncSession, principal: Principal, key: str, value: dict
) -> SystemSetting:
    await session.execute(
        text(
            "INSERT INTO system_setting (org_id, key, value) VALUES (:o, :k, CAST(:v AS jsonb)) "
            "ON CONFLICT (org_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"
        ),
        {"o": principal.org_id, "k": key, "v": json.dumps(value)},
    )
    row = (
        await session.execute(
            select(SystemSetting).where(SystemSetting.key == key)
        )
    ).scalar_one()
    return row


async def feature_flags(session: AsyncSession, principal: Principal) -> dict:
    rows = await list_settings(session, principal)
    return {
        r.key.removeprefix("feature."): bool(r.value.get("enabled", False))
        for r in rows
        if r.key.startswith("feature.")
    }
