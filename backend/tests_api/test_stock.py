"""Stock: adjustments, balances, movements, reorder points, transfers,
verification and the drift reconciler."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from .conftest import uniq

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def product(client, admin, base) -> int:
    """A product of its own, so quantities are asserted without other tests
    moving the shared one underneath."""
    r = await client.post("/api/v1/products", headers=admin, json={
        "name": uniq("Stocked"), "base_unit_id": base["unit"], "gst_rate": "5",
        "sale_price": "100", "purchase_price": "60",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


async def _on_hand(client, admin, product_id, branch=None) -> str:
    r = await client.get("/api/v1/stock/current", headers=admin,
                         params={"product_id": product_id})
    assert r.status_code == 200, r.text
    return r.json()["total_on_hand"]


# ---- adjustments ----------------------------------------------------------
async def test_opening_adjustment_creates_stock_and_cost(client, admin, base, product, idem):
    r = await client.post("/api/v1/stock/adjustments", headers={**admin, **idem}, json={
        "branch_id": base["branch"], "godown_id": base["godown"], "adj_reason": "opening",
        "lines": [{"product_id": product, "entered_qty": "200",
                   "entered_unit_id": base["unit"], "unit_cost": "40"}],
    })
    assert r.status_code in (200, 201), r.text
    assert await _on_hand(client, admin, product) == "200.000000"

    value = await client.get("/api/v1/stock/value", headers=admin,
                             params={"branch_id": base["branch"]})
    assert value.status_code == 200


async def test_decrease_adjustment_reduces_stock(client, admin, base, product, idem):
    await client.post("/api/v1/stock/adjustments", headers={**admin, **idem}, json={
        "branch_id": base["branch"], "godown_id": base["godown"], "adj_reason": "opening",
        "lines": [{"product_id": product, "entered_qty": "100",
                   "entered_unit_id": base["unit"], "unit_cost": "40"}],
    })
    r = await client.post("/api/v1/stock/adjustments",
                          headers={**admin, "Idempotency-Key": str(uuid.uuid4())}, json={
        "branch_id": base["branch"], "godown_id": base["godown"], "adj_reason": "damage",
        "lines": [{"product_id": product, "entered_qty": "30",
                   "entered_unit_id": base["unit"]}],
    })
    assert r.status_code in (200, 201), r.text
    assert await _on_hand(client, admin, product) == "70.000000"


async def test_taking_out_more_than_exists_is_409(client, admin, base, product, idem):
    """The oversell guard is the ledger's whole point; it must surface as a
    conflict, not a 500."""
    r = await client.post("/api/v1/stock/adjustments", headers={**admin, **idem}, json={
        "branch_id": base["branch"], "godown_id": base["godown"], "adj_reason": "shortage",
        "lines": [{"product_id": product, "entered_qty": "999999",
                   "entered_unit_id": base["unit"]}],
    })
    assert r.status_code == 409, r.text


async def test_an_adjustment_needs_a_godown_of_its_branch(client, admin, base, product, idem):
    r = await client.post("/api/v1/stock/adjustments", headers={**admin, **idem}, json={
        "branch_id": base["branch"], "godown_id": 999999, "adj_reason": "opening",
        "lines": [{"product_id": product, "entered_qty": "1",
                   "entered_unit_id": base["unit"], "unit_cost": "1"}],
    })
    assert r.status_code in (403, 422), r.text


async def test_an_adjustment_needs_at_least_one_line(client, admin, base, idem):
    r = await client.post("/api/v1/stock/adjustments", headers={**admin, **idem}, json={
        "branch_id": base["branch"], "godown_id": base["godown"],
        "adj_reason": "opening", "lines": [],
    })
    assert r.status_code == 422


# ---- balances & movements -------------------------------------------------
async def test_current_stock_breaks_down_by_godown(client, admin, base, product, idem):
    await client.post("/api/v1/stock/adjustments", headers={**admin, **idem}, json={
        "branch_id": base["branch"], "godown_id": base["godown"], "adj_reason": "opening",
        "lines": [{"product_id": product, "entered_qty": "50",
                   "entered_unit_id": base["unit"], "unit_cost": "10"}],
    })
    r = await client.get("/api/v1/stock/current", headers=admin, params={"product_id": product})
    body = r.json()
    assert body["total_on_hand"] == "50.000000"
    assert body["by_godown"] and body["by_godown"][0]["godown_id"] == base["godown"]
    assert "available" in body["by_godown"][0]


async def test_movements_are_listed_for_a_product(client, admin, base, product, idem):
    await client.post("/api/v1/stock/adjustments", headers={**admin, **idem}, json={
        "branch_id": base["branch"], "godown_id": base["godown"], "adj_reason": "opening",
        "lines": [{"product_id": product, "entered_qty": "5",
                   "entered_unit_id": base["unit"], "unit_cost": "10"}],
    })
    r = await client.get("/api/v1/stock/movements", headers=admin, params={"product_id": product})
    assert r.status_code == 200
    assert r.json(), "the opening adjustment must appear in the ledger"
    assert r.json()[0]["source_doc_type"] == "stock_adjustment"


async def test_stock_current_requires_a_product(client, admin):
    r = await client.get("/api/v1/stock/current", headers=admin)
    assert r.status_code == 422


# ---- reorder thresholds ---------------------------------------------------
async def test_reorder_threshold_set_and_list(client, admin, product):
    r = await client.post("/api/v1/stock/reorder-thresholds", headers=admin,
                          json={"product_id": product, "min_qty": "25"})
    assert r.status_code in (200, 201), r.text
    listed = await client.get("/api/v1/stock/reorder-thresholds", headers=admin)
    assert listed.status_code == 200
    assert any(t["product_id"] == product for t in listed.json())


# ---- transfers ------------------------------------------------------------
async def test_transfer_within_a_branch_moves_between_godowns(
    client, admin, base, product, idem
):
    if base["godown2"] == base["godown"]:
        pytest.skip("this org has only one godown in the working branch")
    await client.post("/api/v1/stock/adjustments", headers={**admin, **idem}, json={
        "branch_id": base["branch"], "godown_id": base["godown"], "adj_reason": "opening",
        "lines": [{"product_id": product, "entered_qty": "100",
                   "entered_unit_id": base["unit"], "unit_cost": "20"}],
    })

    created = await client.post("/api/v1/stock/transfers", headers=admin, json={
        "from_godown_id": base["godown"], "to_godown_id": base["godown2"],
        "lines": [{"product_id": product, "entered_qty": "30",
                   "entered_unit_id": base["unit"]}],
    })
    assert created.status_code in (200, 201), created.text
    body = created.json()
    tid = body["id"]
    # the branches are derived from the godowns, not sent by the caller
    assert body["from_branch_id"] == body["to_branch_id"] == base["branch"]
    assert body["status"] == "draft"

    disp = await client.post(f"/api/v1/stock/transfers/{tid}/dispatch", headers=admin)
    assert disp.status_code == 200, disp.text
    assert disp.json()["status"] == "dispatched"
    assert disp.json()["lines"][0]["unit_cost"] == "20.000000", "cost is carried on dispatch"

    recv = await client.post(f"/api/v1/stock/transfers/{tid}/receive", headers=admin)
    assert recv.status_code == 200, recv.text
    assert recv.json()["status"] == "received"

    # nothing left the branch, it only moved shelf
    assert await _on_hand(client, admin, product) == "100.000000"
    by_godown = {g["godown_id"]: g["on_hand"] for g in
                 (await client.get("/api/v1/stock/current", headers=admin,
                                   params={"product_id": product})).json()["by_godown"]}
    assert by_godown[base["godown2"]] == "30.000000"


async def test_transfer_to_and_from_the_same_godown_is_refused(client, admin, base, product):
    r = await client.post("/api/v1/stock/transfers", headers=admin, json={
        "from_godown_id": base["godown"], "to_godown_id": base["godown"],
        "lines": [{"product_id": product, "entered_qty": "1", "entered_unit_id": base["unit"]}],
    })
    assert r.status_code == 422, r.text


async def test_transfer_to_an_unreachable_godown_is_refused(client, admin, base, product):
    r = await client.post("/api/v1/stock/transfers", headers=admin, json={
        "from_godown_id": base["godown"], "to_godown_id": 999999,
        "lines": [{"product_id": product, "entered_qty": "1", "entered_unit_id": base["unit"]}],
    })
    assert r.status_code in (403, 422), r.text


async def test_a_transfer_cannot_be_received_before_dispatch(client, admin, base, product, idem):
    if base["godown2"] == base["godown"]:
        pytest.skip("needs two godowns")
    await client.post("/api/v1/stock/adjustments", headers={**admin, **idem}, json={
        "branch_id": base["branch"], "godown_id": base["godown"], "adj_reason": "opening",
        "lines": [{"product_id": product, "entered_qty": "10",
                   "entered_unit_id": base["unit"], "unit_cost": "5"}],
    })
    created = await client.post("/api/v1/stock/transfers", headers=admin, json={
        "from_godown_id": base["godown"], "to_godown_id": base["godown2"],
        "lines": [{"product_id": product, "entered_qty": "5", "entered_unit_id": base["unit"]}],
    })
    tid = created.json()["id"]
    r = await client.post(f"/api/v1/stock/transfers/{tid}/receive", headers=admin)
    assert r.status_code == 422, "a draft has not left anywhere yet"


async def test_transfers_list_filters_by_state(client, admin):
    for state in ("open", "closed", None):
        params = {"state": state} if state else {}
        r = await client.get("/api/v1/stock/transfers", headers=admin, params=params)
        assert r.status_code == 200, r.text
        for row in r.json():
            if state == "open":
                assert row["status"] in ("draft", "dispatched")
            elif state == "closed":
                assert row["status"] in ("received", "cancelled")


async def test_an_unknown_transfer_is_404(client, admin):
    r = await client.post("/api/v1/stock/transfers/99999999/dispatch", headers=admin)
    assert r.status_code == 404


# ---- verification ---------------------------------------------------------
async def test_verification_posts_the_snapshot_delta(client, admin, base, product, idem):
    await client.post("/api/v1/stock/adjustments", headers={**admin, **idem}, json={
        "branch_id": base["branch"], "godown_id": base["godown"], "adj_reason": "opening",
        "lines": [{"product_id": product, "entered_qty": "80",
                   "entered_unit_id": base["unit"], "unit_cost": "10"}],
    })
    created = await client.post("/api/v1/stock/verifications", headers=admin, json={
        "branch_id": base["branch"], "godown_id": base["godown"],
        "lines": [{"product_id": product, "physical_qty": "75"}],
    })
    assert created.status_code in (200, 201), created.text
    vid = created.json()["id"]

    posted = await client.post(f"/api/v1/stock/verifications/{vid}/post", headers=admin)
    assert posted.status_code == 200, posted.text
    line = posted.json()["lines"][0]
    assert line["system_qty_at_start"] == "80.000000"
    assert line["physical_qty"] == "75.000000"
    assert line["delta"] == "-5.000000", "the count is posted as the difference"
    assert await _on_hand(client, admin, product) == "75.000000"


async def test_a_verification_needs_a_godown_of_its_branch(client, admin, base, product):
    """Filing a count against a godown that is not the branch's would measure
    the delta against a balance that is not the one being counted — and it used
    to post silently. (The two-branch case is driven at service level in
    tests/test_branch_transfer.py, where a principal can hold both branches.)"""
    r = await client.post("/api/v1/stock/verifications", headers=admin, json={
        "branch_id": base["branch"], "godown_id": 999999,
        "lines": [{"product_id": product, "physical_qty": "1"}],
    })
    assert r.status_code in (403, 422), r.text


async def test_a_godown_cannot_be_created_in_a_branch_you_do_not_work_in(client, admin):
    """Branches are org-visible, so one you do not work in is nameable — but
    godowns carry branch RLS, and writing into such a branch has to be refused
    up front rather than surfacing as a bare policy failure."""
    other = await client.post("/api/v1/branches", headers=admin, json={"name": uniq("Far")})
    assert other.status_code in (200, 201), other.text
    r = await client.post("/api/v1/godowns", headers=admin,
                          json={"name": uniq("FarStore"), "branch_id": other.json()["id"]})
    assert r.status_code == 403, r.text


# ---- the reconciler -------------------------------------------------------
async def test_reconcile_reports_no_drift(client, admin):
    """The 5-way invariant check, run over everything this suite has posted."""
    r = await client.post("/api/v1/stock/reconcile", headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True, body
    assert body["drift_rows"] == []
    assert body["allocation_drift"] == []
