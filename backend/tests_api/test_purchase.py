"""Purchase: bills, returns, orders, receipts, amendment and payment history."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from .conftest import uniq

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def product(client, admin, base) -> int:
    r = await client.post("/api/v1/products", headers=admin, json={
        "name": uniq("Bought"), "base_unit_id": base["unit"], "gst_rate": "5",
        "purchase_price": "60", "sale_price": "100",
    })
    return r.json()["id"]


def _line(product, base, qty="10", rate="30", **extra):
    return {"product_id": product, "godown_id": base["godown"], "entered_qty": qty,
            "entered_unit_id": base["unit"], "rate": rate, "gst_rate": "5", **extra}


async def _stock(client, admin, product) -> str:
    r = await client.get("/api/v1/stock/current", headers=admin, params={"product_id": product})
    return r.json()["total_on_hand"]


async def _payable(client, admin, party) -> str:
    r = await client.get(f"/api/v1/parties/{party}/ledger", headers=admin)
    return str(r.json()["net_balance"])


# ---- bills ----------------------------------------------------------------
async def test_purchase_bill_moves_stock_and_credits_the_supplier(
    client, admin, base, product, idem
):
    # the suite shares one database, so measure the CHANGE this bill caused
    # rather than an absolute balance another test may have moved
    payable_before = float(await _payable(client, admin, base["supplier"]))
    r = await client.post("/api/v1/purchase/bills", headers={**admin, **idem}, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "godown_id": base["godown"], "lines": [_line(product, base, "100", "30")],
    })
    assert r.status_code in (200, 201), r.text
    bill = r.json()
    # 100 x 30 = 3000 taxable, 5% GST split CGST/SGST, grand 3150
    assert bill["taxable_total"] == "3000.00"
    assert bill["tax_total"] == "150.00"
    assert bill["grand_total"] == "3150.00"
    assert bill["lines"][0]["cgst"] == "75.00" and bill["lines"][0]["sgst"] == "75.00"
    assert bill["lines"][0]["igst"] == "0.00", "supply is always intra now"
    assert bill["supply_type"] == "intra"

    assert await _stock(client, admin, product) == "100.000000"
    # a supplier we owe carries a CREDIT balance, so the net falls by the bill
    assert float(await _payable(client, admin, base["supplier"])) == pytest.approx(
        payable_before - 3150.00
    )


async def test_bill_money_fields_are_decimal_strings_not_floats(client, admin, base, product, idem):
    """The recurring gotcha: a raw dict response renders 1050 instead of
    1050.00 and the screen shows a different number from the document."""
    r = await client.post("/api/v1/purchase/bills", headers={**admin, **idem}, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "godown_id": base["godown"], "lines": [_line(product, base, "10", "100")],
    })
    body = r.json()
    for field in ("grand_total", "taxable_total", "tax_total", "paid_amount", "balance_amount"):
        assert isinstance(body[field], str), f"{field} is {type(body[field])}"
        assert "." in body[field], f"{field} lost its scale: {body[field]}"


async def test_bill_with_payment_settles_and_leaves_a_balance(
    client, admin, base, product, idem
):
    r = await client.post("/api/v1/purchase/bills", headers={**admin, **idem}, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "godown_id": base["godown"], "lines": [_line(product, base, "10", "100")],
        "paid_amount": "500", "payment_account_id": base["account"],
    })
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["grand_total"] == "1050.00"
    assert body["paid_amount"] == "500.00"
    assert body["balance_amount"] == "550.00"

    payments = await client.get(f"/api/v1/purchase/bills/{body['id']}/payments", headers=admin)
    assert payments.status_code == 200, payments.text
    assert payments.json(), "the settlement must appear in the payment history"


async def test_split_payment_across_tenders(client, admin, base, product, idem):
    r = await client.post("/api/v1/purchase/bills", headers={**admin, **idem}, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "godown_id": base["godown"], "lines": [_line(product, base, "10", "100")],
        "payments": [
            {"account_id": base["account"], "payment_type_id": base["payment_type"],
             "amount": "300", "reference": "cash"},
            {"account_id": base["account"], "amount": "200"},
        ],
    })
    assert r.status_code in (200, 201), r.text
    assert r.json()["paid_amount"] == "500.00", "paid is DERIVED from the tenders"


async def test_a_split_that_contradicts_paid_amount_is_refused(
    client, admin, base, product, idem
):
    r = await client.post("/api/v1/purchase/bills", headers={**admin, **idem}, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "godown_id": base["godown"], "lines": [_line(product, base, "10", "100")],
        "paid_amount": "999",
        "payments": [{"account_id": base["account"], "amount": "500"}],
    })
    assert r.status_code == 422, r.text


async def test_paying_more_than_the_bill_is_refused(client, admin, base, product, idem):
    r = await client.post("/api/v1/purchase/bills", headers={**admin, **idem}, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "godown_id": base["godown"], "lines": [_line(product, base, "1", "10")],
        "paid_amount": "100000", "payment_account_id": base["account"],
    })
    assert r.status_code == 422, r.text


async def test_bill_needs_a_known_supplier_and_a_line(client, admin, base, product, idem):
    no_supplier = await client.post("/api/v1/purchase/bills", headers={**admin, **idem}, json={
        "supplier_id": 999999, "branch_id": base["branch"], "godown_id": base["godown"],
        "lines": [_line(product, base)],
    })
    assert no_supplier.status_code == 422, no_supplier.text

    no_lines = await client.post("/api/v1/purchase/bills",
                                 headers={**admin, "Idempotency-Key": str(uuid.uuid4())}, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "godown_id": base["godown"], "lines": [],
    })
    assert no_lines.status_code == 422


async def test_a_bill_cannot_use_an_unreachable_godown(client, admin, base, product, idem):
    """Both the line's godown and the header default it falls back to. The
    header was written to the document without ever being checked."""
    line = {k: v for k, v in _line(product, base).items() if k != "godown_id"}
    on_line = await client.post("/api/v1/purchase/bills", headers={**admin, **idem}, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "lines": [{**line, "godown_id": 999999}],
    })
    assert on_line.status_code in (403, 422), on_line.text

    on_header = await client.post("/api/v1/purchase/bills",
                                  headers={**admin, "Idempotency-Key": str(uuid.uuid4())}, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "godown_id": 999999, "lines": [line],
    })
    assert on_header.status_code in (403, 422), on_header.text

    # ...and even when every line names a good godown, a bad header default is
    # still stored and still resurfaces (a PO's header becomes the bill's)
    header_only = await client.post("/api/v1/purchase/bills",
                                    headers={**admin, "Idempotency-Key": str(uuid.uuid4())}, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "godown_id": 999999, "lines": [_line(product, base)],
    })
    assert header_only.status_code in (403, 422), header_only.text


async def test_bills_list_filters_by_branch(client, admin, base):
    r = await client.get("/api/v1/purchase/bills", headers=admin,
                         params={"branch_id": base["branch"]})
    assert r.status_code == 200
    assert all(b["branch_id"] == base["branch"] for b in r.json())
    for field in ("grand_total", "paid_amount", "balance_amount"):
        assert all(isinstance(b[field], str) for b in r.json()), f"{field} must be a string"


# ---- returns --------------------------------------------------------------
async def test_purchase_return_sends_goods_back_and_reduces_the_payable(
    client, admin, base, product, idem
):
    await client.post("/api/v1/purchase/bills", headers={**admin, **idem}, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "godown_id": base["godown"], "lines": [_line(product, base, "100", "30")],
    })
    before = await _payable(client, admin, base["supplier"])

    r = await client.post("/api/v1/purchase/returns",
                          headers={**admin, "Idempotency-Key": str(uuid.uuid4())}, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "godown_id": base["godown"], "lines": [_line(product, base, "10", "30")],
    })
    assert r.status_code in (200, 201), r.text
    assert r.json()["grand_total"] == "315.00"
    assert await _stock(client, admin, product) == "90.000000"
    # payable falls by exactly the credit note
    assert float(await _payable(client, admin, base["supplier"])) == pytest.approx(
        float(before) + 315.00
    )


async def test_returns_are_listable(client, admin, base):
    r = await client.get("/api/v1/purchase/returns", headers=admin,
                         params={"branch_id": base["branch"]})
    assert r.status_code == 200


# ---- orders ---------------------------------------------------------------
async def test_purchase_order_create_get_and_receive(client, admin, base, product, idem):
    created = await client.post("/api/v1/purchase/orders", headers=admin, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "godown_id": base["godown"],
        "lines": [_line(product, base, "50", "30")],
    })
    assert created.status_code in (200, 201), created.text
    po = created.json()
    poid = po["id"]
    assert po["status"] == "open"
    assert po["grand_total"] == "1575.00"

    got = await client.get(f"/api/v1/purchase/orders/{poid}", headers=admin)
    assert got.status_code == 200
    assert got.json()["lines"][0]["pending_qty"] == "50.000000"

    listed = await client.get("/api/v1/purchase/orders", headers=admin)
    assert listed.status_code == 200 and any(o["id"] == poid for o in listed.json())

    before = await _stock(client, admin, product)
    recv = await client.post(f"/api/v1/purchase/orders/{poid}/receive",
                             headers={**admin, **idem}, json={})
    assert recv.status_code in (200, 201), recv.text
    assert recv.json()["po_id"] == poid, "the bill must link back to the order"
    assert float(await _stock(client, admin, product)) == pytest.approx(float(before) + 50)

    closed = await client.get(f"/api/v1/purchase/orders/{poid}", headers=admin)
    assert closed.json()["status"] == "closed", "fully received closes the order"


async def test_a_received_order_cannot_be_cancelled(client, admin, base, product, idem):
    created = await client.post("/api/v1/purchase/orders", headers=admin, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "godown_id": base["godown"], "lines": [_line(product, base, "5", "30")],
    })
    poid = created.json()["id"]
    await client.post(f"/api/v1/purchase/orders/{poid}/receive", headers={**admin, **idem}, json={})
    r = await client.post(f"/api/v1/purchase/orders/{poid}/cancel", headers=admin)
    assert r.status_code == 422, "goods already arrived; cancelling would strand them"


async def test_a_pending_order_can_be_cancelled(client, admin, base, product):
    created = await client.post("/api/v1/purchase/orders", headers=admin, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "godown_id": base["godown"], "lines": [_line(product, base, "5", "30")],
    })
    poid = created.json()["id"]
    r = await client.post(f"/api/v1/purchase/orders/{poid}/cancel", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"


async def test_an_unknown_order_is_404(client, admin):
    r = await client.get("/api/v1/purchase/orders/99999999", headers=admin)
    assert r.status_code == 404


# ---- amendment (v2 §7) ----------------------------------------------------
async def test_cancelling_a_bill_reverses_stock_and_the_payable(
    client, admin, base, product, idem
):
    posted = await client.post("/api/v1/purchase/bills", headers={**admin, **idem}, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "godown_id": base["godown"], "lines": [_line(product, base, "20", "50")],
    })
    bill = posted.json()
    stock_after_bill = await _stock(client, admin, product)
    payable_after_bill = await _payable(client, admin, base["supplier"])

    r = await client.post(f"/api/v1/purchase/bills/{bill['id']}/cancel", headers=admin,
                          json={"reason": "wrong supplier"})
    assert r.status_code == 200, r.text

    # the goods go back out and the payable returns to what it was
    assert float(await _stock(client, admin, product)) == pytest.approx(
        float(stock_after_bill) - 20
    )
    assert float(await _payable(client, admin, base["supplier"])) == pytest.approx(
        float(payable_after_bill) + float(bill["grand_total"])
    )


async def test_amending_a_bill_replaces_it_with_a_new_revision(
    client, admin, base, product, idem
):
    posted = await client.post("/api/v1/purchase/bills", headers={**admin, **idem}, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "godown_id": base["godown"], "lines": [_line(product, base, "10", "50")],
    })
    old = posted.json()

    r = await client.put(f"/api/v1/purchase/bills/{old['id']}", headers=admin, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "godown_id": base["godown"], "lines": [_line(product, base, "12", "50")],
        "reason": "quantity was wrong",
    })
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["id"] != old["id"], "an amendment posts a NEW document, never edits"
    assert new["grand_total"] == "630.00"  # 12 x 50 = 600 + 5%


async def test_cancelling_twice_is_refused(client, admin, base, product, idem):
    posted = await client.post("/api/v1/purchase/bills", headers={**admin, **idem}, json={
        "supplier_id": base["supplier"], "branch_id": base["branch"],
        "godown_id": base["godown"], "lines": [_line(product, base, "1", "10")],
    })
    bid = posted.json()["id"]
    first = await client.post(f"/api/v1/purchase/bills/{bid}/cancel", headers=admin, json={})
    assert first.status_code == 200, first.text
    second = await client.post(f"/api/v1/purchase/bills/{bid}/cancel", headers=admin, json={})
    assert second.status_code == 409, "already cancelled"
