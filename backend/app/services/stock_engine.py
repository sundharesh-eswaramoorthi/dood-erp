"""The stock posting engine (Phase-2 design §8).

Every primitive runs inside the caller's request transaction (get_scoped_session):
the ledger row and the balance update commit together or not at all. All
quantities are in the product's canonical BASE unit.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class OverSell(Exception):
    """Outbound movement would drive available stock negative."""


async def to_base(session: AsyncSession, product_id: int, entered_qty: Decimal, entered_unit_id: int) -> Decimal:
    base_unit = (
        await session.execute(
            text("SELECT base_unit_id FROM product WHERE id = :p"), {"p": product_id}
        )
    ).scalar_one_or_none()
    if base_unit is None:
        raise ValueError("product not found")
    if entered_unit_id == base_unit:
        return Decimal(entered_qty)
    factor = (
        await session.execute(
            text(
                "SELECT factor_to_base FROM unit_conversion "
                "WHERE product_id = :p AND from_unit_id = :u "
                "ORDER BY effective_from DESC LIMIT 1"
            ),
            {"p": product_id, "u": entered_unit_id},
        )
    ).scalar_one_or_none()
    if factor is None:
        raise ValueError("no unit conversion defined for that unit")
    return Decimal(entered_qty) * Decimal(factor)


async def product_allows_negative(session: AsyncSession, product_id: int) -> bool:
    return bool(
        (
            await session.execute(
                text("SELECT allow_negative_stock FROM product WHERE id = :p"), {"p": product_id}
            )
        ).scalar_one()
    )


async def current_wac(session: AsyncSession, org_id: int, product_id: int, branch_id: int) -> Decimal:
    val = (
        await session.execute(
            text(
                "SELECT moving_avg_cost FROM product_cost "
                "WHERE org_id = :o AND product_id = :p AND branch_id = :b"
            ),
            {"o": org_id, "p": product_id, "b": branch_id},
        )
    ).scalar_one_or_none()
    return Decimal(val) if val is not None else Decimal(0)


async def _lock_cost(session: AsyncSession, org_id: int, product_id: int, branch_id: int):
    await session.execute(
        text(
            "INSERT INTO product_cost (org_id, product_id, branch_id) VALUES (:o, :p, :b) "
            "ON CONFLICT DO NOTHING"
        ),
        {"o": org_id, "p": product_id, "b": branch_id},
    )
    return (
        await session.execute(
            text(
                "SELECT moving_avg_cost, qty_basis FROM product_cost "
                "WHERE org_id = :o AND product_id = :p AND branch_id = :b FOR UPDATE"
            ),
            {"o": org_id, "p": product_id, "b": branch_id},
        )
    ).mappings().one()


async def apply_cost_inbound(
    session: AsyncSession, org_id: int, product_id: int, branch_id: int,
    in_qty: Decimal, in_cost: Decimal,
) -> Decimal:
    row = await _lock_cost(session, org_id, product_id, branch_id)
    old_avg, old_qty = Decimal(row["moving_avg_cost"]), Decimal(row["qty_basis"])
    total = old_qty + in_qty
    new_avg = ((old_avg * old_qty) + (in_cost * in_qty)) / total if total > 0 else in_cost
    await session.execute(
        text(
            "UPDATE product_cost SET moving_avg_cost = :a, qty_basis = :q, version = version + 1, "
            "updated_at = now() WHERE org_id = :o AND product_id = :p AND branch_id = :b"
        ),
        {"a": new_avg, "q": total, "o": org_id, "p": product_id, "b": branch_id},
    )
    return new_avg


async def apply_cost_outbound(
    session: AsyncSession, org_id: int, product_id: int, branch_id: int, out_qty: Decimal
) -> Decimal:
    row = await _lock_cost(session, org_id, product_id, branch_id)
    avg, old_qty = Decimal(row["moving_avg_cost"]), Decimal(row["qty_basis"])
    await session.execute(
        text(
            "UPDATE product_cost SET qty_basis = :q, version = version + 1, updated_at = now() "
            "WHERE org_id = :o AND product_id = :p AND branch_id = :b"
        ),
        {"q": old_qty - out_qty, "o": org_id, "p": product_id, "b": branch_id},
    )
    return avg * out_qty  # COGS


async def move_stock(
    session: AsyncSession,
    *,
    org_id: int,
    branch_id: int,
    godown_id: int,
    product_id: int,
    signed_qty: Decimal,
    movement_type: str,
    cost: Decimal | None,
    source: tuple[str, int, int],
    effective_date,
    created_by: int,
    location_state: str = "on_hand",
    allow_negative: bool = False,
    entry_purpose: str = "original",
    reversal_seq: int = 0,
) -> None:
    """Append one ledger row and update the balance under a row lock."""
    # ensure balance row exists, then lock it
    await session.execute(
        text(
            "INSERT INTO stock_balance (org_id, product_id, branch_id, godown_id, location_state) "
            "VALUES (:o, :p, :b, :g, :s) ON CONFLICT DO NOTHING"
        ),
        {"o": org_id, "p": product_id, "b": branch_id, "g": godown_id, "s": location_state},
    )
    bal = (
        await session.execute(
            text(
                "SELECT on_hand, reserved FROM stock_balance "
                "WHERE org_id = :o AND product_id = :p AND branch_id = :b "
                "AND godown_id = :g AND location_state = :s FOR UPDATE"
            ),
            {"o": org_id, "p": product_id, "b": branch_id, "g": godown_id, "s": location_state},
        )
    ).mappings().one()

    if signed_qty < 0 and not allow_negative:
        available = Decimal(bal["on_hand"]) - Decimal(bal["reserved"])
        if available < -signed_qty:
            raise OverSell(
                f"insufficient stock: available {available}, requested {-signed_qty}"
            )

    src_type, src_id, line_no = source
    await session.execute(
        text(
            "INSERT INTO stock_movement_ledger "
            "(org_id, branch_id, godown_id, product_id, signed_qty, unit_cost, movement_type, "
            " location_state, source_doc_type, source_doc_id, source_line_no, entry_purpose, "
            " reversal_seq, effective_date, created_by) "
            "VALUES (:o, :b, :g, :p, :q, :c, :mt, :s, :st, :sid, :ln, :ep, :rs, :ed, :by)"
        ),
        {
            "o": org_id, "b": branch_id, "g": godown_id, "p": product_id, "q": signed_qty,
            "c": cost, "mt": movement_type, "s": location_state, "st": src_type, "sid": src_id,
            "ln": line_no, "ep": entry_purpose, "rs": reversal_seq,
            "ed": effective_date, "by": created_by,
        },
    )
    await session.execute(
        text(
            "UPDATE stock_balance SET on_hand = on_hand + :q, version = version + 1, updated_at = now() "
            "WHERE org_id = :o AND product_id = :p AND branch_id = :b "
            "AND godown_id = :g AND location_state = :s"
        ),
        {"q": signed_qty, "o": org_id, "p": product_id, "b": branch_id, "g": godown_id, "s": location_state},
    )
