"""Stock moving from one branch to another.

The table always had from_branch_id/to_branch_id and the engine always carried
the moving-average cost across, but nothing chose a destination outside the
caller's own branch and nothing checked the pair was coherent — a transfer could
name a godown belonging to a branch it was not filed against, and stock_balance
is keyed on (branch, godown), so that opens a bucket no other document reaches.

The branch is now read off each godown, which makes the pair impossible to get
wrong and turns "transfer to another branch" into simply choosing a destination
godown that lives in one.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.deps import Principal
from app.modules.stock import service as stock
from app.modules.stock.schemas import (
    TransferCreate,
    TransferLineIn,
    VerificationCreate,
    VerifyLineIn,
)
from app.services import stock_engine as eng

TODAY = dt.date.today()


async def _seed_stock(ctx, qty: Decimal, cost: Decimal) -> None:
    """Goods on hand in the source godown, with a moving-average cost."""
    s, org, branch, godown, product = (
        ctx["s"], ctx["org"], ctx["branch"], ctx["godown"], ctx["product"]
    )
    await eng.move_stock(
        s, org_id=org, branch_id=branch, godown_id=godown, product_id=product,
        signed_qty=qty, movement_type="purchase", cost=cost,
        source=("seed", 9001, 1), effective_date=TODAY, created_by=1,
    )
    await eng.apply_cost_inbound(s, org, product, branch, qty, cost)
    await s.commit()


async def _on_hand(ctx, branch: int, godown: int) -> Decimal:
    row = (
        await ctx["s"].execute(
            text("SELECT COALESCE(on_hand,0) FROM stock_balance WHERE org_id=:o AND product_id=:p "
                 "AND branch_id=:b AND godown_id=:g AND location_state='on_hand'"),
            {"o": ctx["org"], "p": ctx["product"], "b": branch, "g": godown},
        )
    ).scalar_one_or_none()
    return Decimal(row) if row is not None else Decimal(0)


async def _wac(ctx, branch: int) -> Decimal:
    return await eng.current_wac(ctx["s"], ctx["org"], ctx["product"], branch)


def _principal(ctx, branches: list[int]) -> Principal:
    return Principal(user_id=1, org_id=ctx["org"], branch_ids=branches, perms={"*"}, name="t")


async def test_stock_crosses_to_another_branch_carrying_its_cost(ctx):
    """Dispatch takes the goods out of the source at its moving average and
    receive puts them into the destination at that carried cost, so value
    travels with the goods instead of being re-derived at the far end."""
    s = ctx["s"]
    src_branch, dst_branch = ctx["branch"], ctx["branch2"]
    src_godown, dst_godown = ctx["godown"], ctx["godown3"]
    prin = _principal(ctx, [src_branch, dst_branch])

    await _seed_stock(ctx, Decimal(100), Decimal(20))
    assert await _wac(ctx, src_branch) == Decimal(20)
    assert await _wac(ctx, dst_branch) == Decimal(0)   # nothing there yet

    tr = await stock.create_transfer(s, prin, TransferCreate(
        from_godown_id=src_godown, to_godown_id=dst_godown,
        lines=[TransferLineIn(product_id=ctx["product"], entered_qty=Decimal(30),
                              entered_unit_id=ctx["unit"])],
    ))
    await s.commit()
    # neither branch was named by the caller — both came off the godowns
    assert tr["from_branch_id"] == src_branch
    assert tr["to_branch_id"] == dst_branch

    await stock.dispatch_transfer(s, prin, tr["id"])
    await s.commit()
    # goods have left the source; they are not at the destination yet
    assert await _on_hand(ctx, src_branch, src_godown) == Decimal(70)
    assert await _on_hand(ctx, dst_branch, dst_godown) == Decimal(0)

    await stock.receive_transfer(s, prin, tr["id"])
    await s.commit()
    assert await _on_hand(ctx, src_branch, src_godown) == Decimal(70)
    assert await _on_hand(ctx, dst_branch, dst_godown) == Decimal(30)

    # the cost crossed with them: the destination now values this product at
    # what the source held it at, not at zero
    assert await _wac(ctx, dst_branch) == Decimal(20)
    assert await _wac(ctx, src_branch) == Decimal(20)   # unchanged by the move

    # T1 still holds on BOTH sides: on_hand == SUM(ledger) per branch+godown
    for branch, godown in ((src_branch, src_godown), (dst_branch, dst_godown)):
        ledger = Decimal(
            (await s.execute(
                text("SELECT COALESCE(SUM(signed_qty),0) FROM stock_movement_ledger "
                     "WHERE org_id=:o AND product_id=:p AND branch_id=:b AND godown_id=:g"),
                {"o": ctx["org"], "p": ctx["product"], "b": branch, "g": godown},
            )).scalar_one()
        )
        assert ledger == await _on_hand(ctx, branch, godown)


async def test_a_transfer_within_one_branch_still_works(ctx):
    """The same document, both feet in one branch — the WAC is per branch, so
    nothing about the cost should move at all."""
    s, branch = ctx["s"], ctx["branch"]
    prin = _principal(ctx, [branch])
    await _seed_stock(ctx, Decimal(50), Decimal(8))

    tr = await stock.create_transfer(s, prin, TransferCreate(
        from_godown_id=ctx["godown"], to_godown_id=ctx["godown2"],
        lines=[TransferLineIn(product_id=ctx["product"], entered_qty=Decimal(20),
                              entered_unit_id=ctx["unit"])],
    ))
    await s.commit()
    assert tr["from_branch_id"] == tr["to_branch_id"] == branch

    await stock.dispatch_transfer(s, prin, tr["id"])
    await stock.receive_transfer(s, prin, tr["id"])
    await s.commit()

    assert await _on_hand(ctx, branch, ctx["godown"]) == Decimal(30)
    assert await _on_hand(ctx, branch, ctx["godown2"]) == Decimal(20)
    assert await _wac(ctx, branch) == Decimal(8)


async def test_a_godown_outside_your_branches_is_refused(ctx):
    """The destination decides the branch, so an unreachable godown has to be
    caught at creation — otherwise it posts and then dies inside the RLS policy
    on stock_balance as a bare 500."""
    s = ctx["s"]
    prin = _principal(ctx, [ctx["branch"]])   # this user does NOT work in branch2
    await _seed_stock(ctx, Decimal(10), Decimal(5))

    with pytest.raises(PermissionError, match="destination branch"):
        await stock.create_transfer(s, prin, TransferCreate(
            from_godown_id=ctx["godown"], to_godown_id=ctx["godown3"],
            lines=[TransferLineIn(product_id=ctx["product"], entered_qty=Decimal(5),
                                  entered_unit_id=ctx["unit"])],
        ))
    await s.rollback()


async def test_the_same_godown_at_both_ends_is_refused(ctx):
    s = ctx["s"]
    prin = _principal(ctx, [ctx["branch"]])
    with pytest.raises(ValueError, match="must differ"):
        await stock.create_transfer(s, prin, TransferCreate(
            from_godown_id=ctx["godown"], to_godown_id=ctx["godown"],
            lines=[TransferLineIn(product_id=ctx["product"], entered_qty=Decimal(1),
                                  entered_unit_id=ctx["unit"])],
        ))
    await s.rollback()


async def test_receiving_into_a_branch_you_left_is_refused(ctx):
    """A transfer is org-visible because it spans two branches, so somebody who
    works in neither could reach it. The stock move itself is branch-scoped, so
    the refusal has to be explicit rather than left to the policy."""
    s = ctx["s"]
    full = _principal(ctx, [ctx["branch"], ctx["branch2"]])
    await _seed_stock(ctx, Decimal(40), Decimal(12))

    tr = await stock.create_transfer(s, full, TransferCreate(
        from_godown_id=ctx["godown"], to_godown_id=ctx["godown3"],
        lines=[TransferLineIn(product_id=ctx["product"], entered_qty=Decimal(10),
                              entered_unit_id=ctx["unit"])],
    ))
    await stock.dispatch_transfer(s, full, tr["id"])
    await s.commit()

    source_only = _principal(ctx, [ctx["branch"]])
    with pytest.raises(PermissionError, match="arriving"):
        await stock.receive_transfer(s, source_only, tr["id"])
    await s.rollback()

    # the goods are still in transit — nothing was half-applied
    assert await _on_hand(ctx, ctx["branch"], ctx["godown"]) == Decimal(30)
    assert await _on_hand(ctx, ctx["branch2"], ctx["godown3"]) == Decimal(0)


# ---- the branch a document is filed against ----
#
# V2.16 gave every document screen a branch filter and scoped its godown list
# to the chosen branch, but the create payloads never sent that branch. The
# server fell back to principal.branch_ids[0], so working in any branch other
# than your first one either failed outright (where the godown is validated
# against the branch) or, worse, filed the document against the wrong branch
# without saying anything.


async def test_a_purchase_bill_is_filed_against_the_branch_it_names(ctx):
    """The bill posts into the named branch and its stock lands there — not in
    whichever branch happens to be first in the caller's list."""
    from app.modules.purchase import service as purchase
    from app.modules.purchase.schemas import BillLineIn, PurchaseBillCreate

    s = ctx["s"]
    # branch_ids[0] is the FIRST branch; the bill names the second
    prin = _principal(ctx, [ctx["branch"], ctx["branch2"]])

    bill = await purchase.post_bill(s, prin, PurchaseBillCreate(
        supplier_id=ctx["party"], branch_id=ctx["branch2"], godown_id=ctx["godown3"],
        lines=[BillLineIn(product_id=ctx["product"], entered_qty=Decimal(20),
                          entered_unit_id=ctx["unit"], rate=Decimal(30), gst_rate=Decimal(5))],
    ))
    await s.commit()

    # goods are in the named branch, and nowhere else
    assert await _on_hand(ctx, ctx["branch2"], ctx["godown3"]) == Decimal(20)
    assert await _on_hand(ctx, ctx["branch"], ctx["godown"]) == Decimal(0)
    # cost basis follows the goods: 30 ex-tax per unit
    assert await _wac(ctx, ctx["branch2"]) == Decimal(30)
    assert bill["grand_total"] == Decimal("630.00")   # 600 + 5% GST


async def test_a_godown_from_another_branch_is_refused_not_mis_filed(ctx):
    """Naming branch A but a godown of branch B has to be refused. stock_balance
    is keyed on (branch, godown), so the pair would open a bucket that no other
    document can reach."""
    from app.modules.purchase import service as purchase
    from app.modules.purchase.schemas import BillLineIn, PurchaseBillCreate

    s = ctx["s"]
    prin = _principal(ctx, [ctx["branch"], ctx["branch2"]])

    with pytest.raises(ValueError, match="not an active godown of branch"):
        await purchase.post_bill(s, prin, PurchaseBillCreate(
            supplier_id=ctx["party"], branch_id=ctx["branch"], godown_id=ctx["godown3"],
            lines=[BillLineIn(product_id=ctx["product"], entered_qty=Decimal(1),
                              entered_unit_id=ctx["unit"], rate=Decimal(10))],
        ))
    await s.rollback()


async def test_a_verification_cannot_count_a_godown_of_another_branch(ctx):
    """This one used to post silently: the count was filed against the caller's
    first branch while naming a godown belonging to another, so the delta was
    measured against a balance that was not the one being counted."""
    s = ctx["s"]
    prin = _principal(ctx, [ctx["branch"], ctx["branch2"]])

    with pytest.raises(ValueError, match="not an active godown of branch"):
        await stock.create_verification(s, prin, VerificationCreate(
            branch_id=ctx["branch"], godown_id=ctx["godown3"],
            lines=[VerifyLineIn(product_id=ctx["product"], physical_qty=Decimal(5))],
        ))
    await s.rollback()
