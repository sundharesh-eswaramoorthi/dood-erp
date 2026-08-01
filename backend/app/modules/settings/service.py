from __future__ import annotations

import json

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.models.settings import SystemSetting, TagDefinition, TaxRate
from app.modules.settings.schemas import TagCreate, TaxRateCreate


# ---- branches & godowns (v2 §9 / §2 admin) ----
BRANCH_COLS = "id, name, code, address, phone, gstin, state_code, is_active"
GODOWN_COLS = "id, name, branch_id, code, is_active"


async def list_branches(
    session: AsyncSession, principal: Principal, include_inactive: bool = False
) -> list[dict]:
    rows = (
        await session.execute(
            text(
                f"SELECT {BRANCH_COLS} FROM branch WHERE org_id = :o "
                f"{'' if include_inactive else 'AND is_active '}ORDER BY name"
            ),
            {"o": principal.org_id},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def create_branch(session: AsyncSession, principal: Principal, data) -> dict:
    try:
        row = (
            await session.execute(
                text(
                    "INSERT INTO branch (org_id, name, code, address, phone, gstin, state_code, is_active) "
                    f"VALUES (:o,:n,:c,:a,:p,:g,:s,:act) RETURNING {BRANCH_COLS}"
                ),
                {"o": principal.org_id, "n": data.name, "c": data.code, "a": data.address,
                 "p": data.phone, "g": data.gstin, "s": data.state_code, "act": data.is_active},
            )
        ).mappings().one()
    except IntegrityError as e:
        raise ValueError(f"A branch named '{data.name}' (or that code) already exists") from e
    return dict(row)


async def update_branch(session: AsyncSession, principal: Principal, branch_id: int, data) -> dict:
    fields = data.model_dump(exclude_unset=True)
    if fields.get("is_active") is False:
        await _assert_branch_can_deactivate(session, principal, branch_id)
    sets, params = _assignments(fields, {"name", "is_active"})
    if not sets:
        return await get_branch(session, principal, branch_id)
    params |= {"i": branch_id, "o": principal.org_id}
    try:
        row = (
            await session.execute(
                text(f"UPDATE branch SET {', '.join(sets)} WHERE id=:i AND org_id=:o RETURNING {BRANCH_COLS}"),
                params,
            )
        ).mappings().one_or_none()
    except IntegrityError as e:
        raise ValueError("Another branch already uses that name or code") from e
    if row is None:
        raise LookupError("Branch not found")
    return dict(row)


async def get_branch(session: AsyncSession, principal: Principal, branch_id: int) -> dict:
    row = (
        await session.execute(
            text(f"SELECT {BRANCH_COLS} FROM branch WHERE id=:i AND org_id=:o"),
            {"i": branch_id, "o": principal.org_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise LookupError("Branch not found")
    return dict(row)


async def _assert_branch_can_deactivate(
    session: AsyncSession, principal: Principal, branch_id: int
) -> None:
    """Closing a branch that still holds stock would strand it — the goods would
    vanish from every godown list while the ledger still counts them."""
    qty = (
        await session.execute(
            text(
                "SELECT COALESCE(SUM(on_hand),0) FROM stock_balance "
                "WHERE org_id=:o AND branch_id=:b AND location_state='on_hand'"
            ),
            {"o": principal.org_id, "b": branch_id},
        )
    ).scalar_one()
    if qty and qty != 0:
        raise ValueError(
            f"Branch still holds {qty} units of stock — transfer it out before deactivating"
        )


async def list_godowns(
    session: AsyncSession,
    principal: Principal,
    include_inactive: bool = False,
    all_branches: bool = False,
) -> list[dict]:
    clauses = ["org_id = :o"]
    params: dict = {"o": principal.org_id}
    if not include_inactive:
        clauses.append("is_active")
    if not all_branches:
        clauses.append("branch_id = ANY(:b)")
        params["b"] = principal.branch_ids or [-1]
    rows = (
        await session.execute(
            text(f"SELECT {GODOWN_COLS} FROM godown WHERE {' AND '.join(clauses)} ORDER BY name"),
            params,
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def create_godown(session: AsyncSession, principal: Principal, data) -> dict:
    await get_branch(session, principal, data.branch_id)  # 404s if not ours
    try:
        row = (
            await session.execute(
                text(
                    "INSERT INTO godown (org_id, branch_id, name, code, is_active) "
                    f"VALUES (:o,:b,:n,:c,:act) RETURNING {GODOWN_COLS}"
                ),
                {"o": principal.org_id, "b": data.branch_id, "n": data.name,
                 "c": data.code, "act": data.is_active},
            )
        ).mappings().one()
    except IntegrityError as e:
        raise ValueError(f"Branch already has a godown named '{data.name}'") from e
    return dict(row)


async def update_godown(session: AsyncSession, principal: Principal, godown_id: int, data) -> dict:
    fields = data.model_dump(exclude_unset=True)
    if fields.get("branch_id") is not None:
        await get_branch(session, principal, fields["branch_id"])
        await _assert_godown_empty(session, principal, godown_id, "move it to another branch")
    if fields.get("is_active") is False:
        await _assert_godown_empty(session, principal, godown_id, "deactivate it")

    sets, params = _assignments(fields, {"name", "branch_id", "is_active"})
    if not sets:
        return await _get_godown(session, principal, godown_id)
    params |= {"i": godown_id, "o": principal.org_id}
    try:
        row = (
            await session.execute(
                text(f"UPDATE godown SET {', '.join(sets)} WHERE id=:i AND org_id=:o RETURNING {GODOWN_COLS}"),
                params,
            )
        ).mappings().one_or_none()
    except IntegrityError as e:
        raise ValueError("That branch already has a godown with this name") from e
    if row is None:
        raise LookupError("Godown not found")
    return dict(row)


async def _get_godown(session: AsyncSession, principal: Principal, godown_id: int) -> dict:
    row = (
        await session.execute(
            text(f"SELECT {GODOWN_COLS} FROM godown WHERE id=:i AND org_id=:o"),
            {"i": godown_id, "o": principal.org_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise LookupError("Godown not found")
    return dict(row)


async def _assert_godown_empty(
    session: AsyncSession, principal: Principal, godown_id: int, action: str
) -> None:
    """Stock is held per (branch, godown); moving or closing a godown that still
    holds goods would orphan those balances."""
    qty = (
        await session.execute(
            text(
                "SELECT COALESCE(SUM(on_hand),0) FROM stock_balance "
                "WHERE org_id=:o AND godown_id=:g AND location_state='on_hand'"
            ),
            {"o": principal.org_id, "g": godown_id},
        )
    ).scalar_one()
    if qty and qty != 0:
        raise ValueError(f"Godown still holds {qty} units — transfer the stock out before you {action}")


def _assignments(fields: dict, non_nullable: set[str]) -> tuple[list[str], dict]:
    """Build a SET clause from the fields actually sent; an explicit null on a
    NOT NULL column means "leave alone", not "wipe"."""
    sets, params = [], {}
    for i, (key, value) in enumerate(fields.items()):
        if value is None and key in non_nullable:
            continue
        sets.append(f"{key} = :v{i}")
        params[f"v{i}"] = value
    return sets, params


# ---- document types (v2 §9 "Add documents (customisable)") ----
DOCTYPE_COLS = "id, name, applies_to, is_required, is_active, sort_order"


async def list_document_types(
    session: AsyncSession, principal: Principal, applies_to: str | None = None,
    include_inactive: bool = False,
) -> list[dict]:
    clauses = ["org_id = :o"]
    params: dict = {"o": principal.org_id}
    if applies_to:
        clauses.append("applies_to = :a")
        params["a"] = applies_to
    if not include_inactive:
        clauses.append("is_active")
    rows = (
        await session.execute(
            text(
                f"SELECT {DOCTYPE_COLS} FROM document_type WHERE {' AND '.join(clauses)} "
                "ORDER BY applies_to, sort_order, name"
            ),
            params,
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def create_document_type(session: AsyncSession, principal: Principal, data) -> dict:
    try:
        row = (
            await session.execute(
                text(
                    "INSERT INTO document_type (org_id, name, applies_to, is_required, sort_order) "
                    f"VALUES (:o,:n,:a,:r,:s) RETURNING {DOCTYPE_COLS}"
                ),
                {"o": principal.org_id, "n": data.name, "a": data.applies_to,
                 "r": data.is_required, "s": data.sort_order},
            )
        ).mappings().one()
    except IntegrityError as e:
        raise ValueError(f"Document type '{data.name}' already exists") from e
    return dict(row)


async def update_document_type(
    session: AsyncSession, principal: Principal, doc_type_id: int, data
) -> dict:
    fields = data.model_dump(exclude_unset=True)
    sets, params = _assignments(fields, {"name", "is_required", "is_active", "sort_order"})
    if not sets:
        raise ValueError("nothing to update")
    params |= {"i": doc_type_id, "o": principal.org_id}
    try:
        row = (
            await session.execute(
                text(
                    f"UPDATE document_type SET {', '.join(sets)} "
                    f"WHERE id=:i AND org_id=:o RETURNING {DOCTYPE_COLS}"
                ),
                params,
            )
        ).mappings().one_or_none()
    except IntegrityError as e:
        raise ValueError("Another document type already uses that name") from e
    if row is None:
        raise LookupError("Document type not found")
    return dict(row)


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
