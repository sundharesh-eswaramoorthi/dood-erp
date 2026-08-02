"""Master-data behaviour added in V2.12.

Covers the three things that changed shape rather than just moving: an optional
product code, the address/contact block that now posts with its party, and the
numbering series becoming editable.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.core.deps import Principal
from app.modules.parties import service as parties
from app.modules.parties.schemas import (
    AddressCreate,
    ContactCreate,
    PartyCreate,
    PartyUpdate,
)
from app.modules.products import service as products
from app.modules.products.schemas import ProductCreate
from app.modules.settings import service as settings
from app.modules.settings.schemas import NumberingSeriesUpdate


def _principal(ctx) -> Principal:
    return Principal(user_id=1, org_id=ctx["org"], branch_ids=[ctx["branch"]], perms={"*"})


async def test_product_code_is_optional_and_allocated(ctx):
    p = _principal(ctx)
    auto = await products.create_product(
        ctx["s"], p, ProductCreate(name="No code given", base_unit_id=ctx["unit"]),
    )
    assert auto.code == "PRD-0001"
    # blank string counts as "number it for me", not as an empty code
    blank = await products.create_product(
        ctx["s"], p, ProductCreate(code="   ", name="Blank code", base_unit_id=ctx["unit"]),
    )
    assert blank.code == "PRD-0002"
    # an explicit code is still honoured and still has to be unique
    typed = await products.create_product(
        ctx["s"], p, ProductCreate(code="RICE-1", name="Typed", base_unit_id=ctx["unit"]),
    )
    assert typed.code == "RICE-1"
    with pytest.raises(ValueError, match="already exists"):
        await products.create_product(
            ctx["s"], p, ProductCreate(code="RICE-1", name="Dup", base_unit_id=ctx["unit"]),
        )


async def test_opening_stock_lands_in_the_named_branch_and_godown(ctx):
    p = _principal(ctx)
    prod = await products.create_product(
        ctx["s"], p,
        ProductCreate(name="Opening into G2", base_unit_id=ctx["unit"], opening_qty=Decimal(40),
                      opening_rate=Decimal(25), opening_branch_id=ctx["branch"],
                      opening_godown_id=ctx["godown2"]),
    )
    row = (
        await ctx["s"].execute(
            text("SELECT branch_id, godown_id, on_hand FROM stock_balance WHERE product_id=:p"),
            {"p": prod.id},
        )
    ).mappings().one()
    assert row["branch_id"] == ctx["branch"]
    assert row["godown_id"] == ctx["godown2"]
    assert Decimal(row["on_hand"]) == Decimal(40)


async def test_opening_rejects_a_godown_from_another_branch(ctx):
    """stock_balance is keyed on (branch, godown) — a mismatched pair would open
    a bucket no other document could reach."""
    p = _principal(ctx)
    other = (
        await ctx["s"].execute(
            text("INSERT INTO branch (org_id, name) VALUES (:o,'Other') RETURNING id"),
            {"o": ctx["org"]},
        )
    ).scalar_one()
    foreign_godown = (
        await ctx["s"].execute(
            text("INSERT INTO godown (org_id, branch_id, name) VALUES (:o,:b,'Foreign') RETURNING id"),
            {"o": ctx["org"], "b": other},
        )
    ).scalar_one()
    with pytest.raises(ValueError, match="not an active godown of branch"):
        await products.create_product(
            ctx["s"], p,
            ProductCreate(name="Bad pair", base_unit_id=ctx["unit"], opening_qty=Decimal(5),
                          opening_rate=Decimal(10), opening_branch_id=ctx["branch"],
                          opening_godown_id=foreign_godown),
        )


async def test_party_posts_with_its_address_and_contacts(ctx):
    p = _principal(ctx)
    party = await parties.create_party(
        ctx["s"], p,
        PartyCreate(
            name="Nested Traders", area="Erode", serving_branch_id=ctx["branch"],
            address=AddressCreate(line1="12 Mill Road", city="Erode",
                                  map_link="https://www.google.com/maps/@11.3410,77.7172,15z"),
            contacts=[ContactCreate(name="Murugan", relationship="Owner"),
                      ContactCreate(name="Selvi", relationship="Accountant")],
        ),
        None,
    )
    addresses = await parties.list_addresses(ctx["s"], party.id)
    contacts = await parties.list_contacts(ctx["s"], party.id)
    assert len(addresses) == 1 and len(contacts) == 2
    # coordinates come out of the pasted link so a delivery run has them
    assert addresses[0].lat == Decimal("11.3410000")
    assert addresses[0].lng == Decimal("77.7172000")
    # first contact becomes primary when none is marked
    assert [c.is_primary for c in contacts] == [True, False]


@pytest.mark.parametrize(
    "link, lat",
    [
        ("https://www.google.com/maps/@11.3410,77.7172,15z", Decimal("11.3410000")),
        ("https://maps.google.com/?q=11.3410,77.7172", Decimal("11.3410000")),
        ("https://www.google.com/maps/place/X/data=!3d11.3410!4d77.7172", Decimal("11.3410000")),
        ("https://maps.app.goo.gl/abc123", None),          # short link carries nothing
    ],
)
async def test_map_link_geo_extraction(ctx, link, lat):
    p = _principal(ctx)
    party = await parties.create_party(
        ctx["s"], p,
        PartyCreate(name=f"Geo {link[-6:]}", area="Erode", serving_branch_id=ctx["branch"],
                    address=AddressCreate(line1="1 Road", map_link=link)),
        None,
    )
    addresses = await parties.list_addresses(ctx["s"], party.id)
    assert addresses[0].lat == lat
    assert addresses[0].map_link == link          # kept verbatim either way


async def test_numbering_prefix_is_editable_but_the_counter_only_moves_forward(ctx):
    p = _principal(ctx)
    series = [s for s in await settings.list_numbering(ctx["s"], p) if s["doc_type"] == "party"][0]
    assert series["sample"] == "CUST-0001"

    out = await settings.update_numbering(
        ctx["s"], p, series["id"], NumberingSeriesUpdate(prefix="PTY/", pad_width=5),
    )
    assert out["sample"] == "PTY/00001"

    party = await parties.create_party(
        ctx["s"], p,
        PartyCreate(name="After rename", area="Erode", serving_branch_id=ctx["branch"]), None,
    )
    assert party.party_code == "PTY/00001"

    # winding the counter back would re-issue numbers already printed
    with pytest.raises(ValueError, match="only move forward"):
        await settings.update_numbering(
            ctx["s"], p, series["id"], NumberingSeriesUpdate(next_value=1),
        )
    # forward is fine — leaving a gap on purpose is a legitimate thing to do
    out = await settings.update_numbering(
        ctx["s"], p, series["id"], NumberingSeriesUpdate(next_value=500),
    )
    assert out["sample"] == "PTY/00500"


async def test_a_party_must_name_a_branch_the_user_works_in(ctx):
    """The branch was optional and fell back to the caller's first one, so a
    party could be filed against a branch nobody chose. It is now required, and
    checked against the caller's access rather than merely the organisation."""
    p = _principal(ctx)
    with pytest.raises(ValidationError):
        PartyCreate(name="No branch", area="Erode")

    other = (
        await ctx["s"].execute(
            text("INSERT INTO branch (org_id, name) VALUES (:o,'Elsewhere') RETURNING id"),
            {"o": ctx["org"]},
        )
    ).scalar_one()
    # exists in the org, but this user does not work there
    with pytest.raises(PermissionError, match="do not have access"):
        await parties.create_party(
            ctx["s"], p,
            PartyCreate(name="Wrong branch", area="Erode", serving_branch_id=other), None,
        )
    with pytest.raises(ValueError, match="not found in this organisation"):
        await parties.create_party(
            ctx["s"], p,
            PartyCreate(name="Bogus branch", area="Erode", serving_branch_id=999_999), None,
        )

    ok = await parties.create_party(
        ctx["s"], p,
        PartyCreate(name="Right branch", area="Erode", serving_branch_id=ctx["branch"]), None,
    )
    assert ok.serving_branch_id == ctx["branch"]


async def test_a_party_cannot_be_moved_to_an_unreachable_branch(ctx):
    p = _principal(ctx)
    other = (
        await ctx["s"].execute(
            text("INSERT INTO branch (org_id, name) VALUES (:o,'Elsewhere') RETURNING id"),
            {"o": ctx["org"]},
        )
    ).scalar_one()
    party = await parties.create_party(
        ctx["s"], p,
        PartyCreate(name="Movable", area="Erode", serving_branch_id=ctx["branch"]), None,
    )
    with pytest.raises(PermissionError, match="do not have access"):
        await parties.update_party(
            ctx["s"], p, party.id, PartyUpdate(serving_branch_id=other),
        )
