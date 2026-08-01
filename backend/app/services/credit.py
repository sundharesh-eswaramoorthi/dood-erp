"""Credit-limit enforcement (v2 §1).

party.credit_limit has existed since Phase 1 but nothing ever read it. v2 lists
it as a party field, so it now gates the two places where a customer's exposure
actually grows: confirming a sale order and posting a sales bill.

NULL / 0 credit_limit == no limit. The check is a hard block by default; set the
system_setting `feature.credit_limit_block` to {"enabled": false} to downgrade
it to advisory (the caller then just logs the breach).
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class CreditLimitExceeded(Exception):
    """Posting this document would push the party past its credit limit."""

    def __init__(self, party_name: str, limit: Decimal, outstanding: Decimal, additional: Decimal):
        self.party_name = party_name
        self.limit = limit
        self.outstanding = outstanding
        self.additional = additional
        super().__init__(
            f"Credit limit exceeded for {party_name}: limit {limit}, "
            f"outstanding {outstanding}, this document {additional} "
            f"(would be {outstanding + additional})"
        )


async def blocking_enabled(session: AsyncSession, org_id: int) -> bool:
    """Default ON — unlike the feature.* flags, absence means "enforce"."""
    row = (
        await session.execute(
            text(
                "SELECT value->>'enabled' AS enabled FROM system_setting "
                "WHERE org_id = :o AND key = 'feature.credit_limit_block'"
            ),
            {"o": org_id},
        )
    ).scalar_one_or_none()
    return row != "false"


async def check(
    session: AsyncSession, org_id: int, party_id: int, additional: Decimal
) -> None:
    """Raise CreditLimitExceeded if `additional` would breach the party's limit.

    Exposure is the receivable side only: what they already owe us plus what
    this document adds. Payables (we owe them) never consume customer credit.
    """
    row = (
        await session.execute(
            text("SELECT name, credit_limit FROM party WHERE id = :p"),
            {"p": party_id},
        )
    ).mappings().first()
    if row is None or row["credit_limit"] is None:
        return
    limit = Decimal(row["credit_limit"])
    if limit <= 0:
        return

    outstanding = Decimal(
        (
            await session.execute(
                text(
                    "SELECT COALESCE(receivable, 0) FROM party_balance "
                    "WHERE org_id = :o AND party_id = :p"
                ),
                {"o": org_id, "p": party_id},
            )
        ).scalar()
        or 0
    )
    if outstanding + additional <= limit:
        return
    if not await blocking_enabled(session, org_id):
        return
    raise CreditLimitExceeded(row["name"], limit, outstanding, additional)
