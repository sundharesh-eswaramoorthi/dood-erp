"""Sales: orders and reservations, deliveries, bills (from an order and off the
counter), returns, and amendment.

Decision #5 — whoever moves the goods first is the sole mover — is the rule
these tests exist to defend, because it is the one that double-counts stock if
it ever slips.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from .conftest import uniq

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def product(client, admin, base, idem) -> int:
    """A product with its own 500 units, so quantities are unambiguous."""
    r = await client.post("/api/v1/products", headers=admin, json={
        "name": uniq("Sold"), "base_unit_id": base["unit"], "gst_rate": "5",
        "sale_price": "100", "purchase_price": "50",
    })
    pid = r.json()["id"]
    await client.post("/api/v1/stock/adjustments", headers={**admin, **idem}, json={
        "branch_id": base["branch"], "godown_id": base["godown"], "adj_reason": "opening",
        "lines": [{"product_id": pid, "entered_qty": "500",
                   "entered_unit_id": base["unit"], "unit_cost": "50"}],
    })
    return pid


def _line(product, base, qty="10", rate="100", **extra):
    return {"product_id": product, "godown_id": base["godown"], "entered_qty": qty,
            "entered_unit_id": base["unit"], "rate": rate, "gst_rate": "5", **extra}


async def _balance(client, admin, product):
    r = await client.get("/api/v1/stock/current", headers=admin, params={"product_id": product})
    b = r.json()
    return b["total_on_hand"], b["total_reserved"], b["total_available"]


# ---- orders ---------------------------------------------------------------
async def test_sale_order_reserves_without_moving(client, admin, base, product):
    r = await client.post("/api/v1/sales/orders", headers=admin, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [_line(product, base, "40")],
    })
    assert r.status_code in (200, 201), r.text
    order = r.json()
    assert order["status"] == "pending"
    assert order["grand_total"] == "4200.00"  # 40 x 100 + 5%

    on_hand, reserved, available = await _balance(client, admin, product)
    assert on_hand == "500.000000", "an order must NOT move goods"
    assert reserved == "40.000000"
    assert available == "460.000000"


async def test_reserving_more_than_available_is_409(client, admin, base, product):
    r = await client.post("/api/v1/sales/orders", headers=admin, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [_line(product, base, "99999")],
    })
    assert r.status_code == 409, r.text


async def test_cancelling_an_order_releases_the_reservation(client, admin, base, product):
    created = await client.post("/api/v1/sales/orders", headers=admin, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [_line(product, base, "25")],
    })
    oid = created.json()["id"]
    _, reserved_before, _ = await _balance(client, admin, product)
    assert reserved_before == "25.000000"

    r = await client.post(f"/api/v1/sales/orders/{oid}/cancel", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"
    _, reserved_after, _ = await _balance(client, admin, product)
    assert reserved_after == "0.000000"


async def test_order_get_and_list(client, admin, base, product):
    created = await client.post("/api/v1/sales/orders", headers=admin, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [_line(product, base, "5")],
    })
    oid = created.json()["id"]
    got = await client.get(f"/api/v1/sales/orders/{oid}", headers=admin)
    assert got.status_code == 200 and got.json()["id"] == oid

    listed = await client.get("/api/v1/sales/orders", headers=admin,
                              params={"branch_id": base["branch"]})
    assert listed.status_code == 200 and any(o["id"] == oid for o in listed.json())


async def test_an_unknown_order_is_404(client, admin):
    r = await client.get("/api/v1/sales/orders/99999999", headers=admin)
    assert r.status_code == 404


# ---- delivery: the sole mover --------------------------------------------
async def test_delivery_dispatch_moves_the_goods_exactly_once(client, admin, base, product):
    order = (await client.post("/api/v1/sales/orders", headers=admin, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [_line(product, base, "30")],
    })).json()
    oid = order["id"]

    created = await client.post("/api/v1/sales/deliveries", headers=admin, json={
        "sale_order_id": oid, "lines": [{"sale_order_line_no": 1, "qty": "30"}],
    })
    assert created.status_code in (200, 201), created.text
    did = created.json()["id"]
    assert created.json()["status"] == "draft"

    disp = await client.post(f"/api/v1/sales/deliveries/{did}/dispatch", headers=admin)
    assert disp.status_code == 200, disp.text
    on_hand, reserved, _ = await _balance(client, admin, product)
    assert on_hand == "470.000000", "the dispatch is what moves stock"
    assert reserved == "0.000000", "and it consumes the reservation"

    done = await client.post(f"/api/v1/sales/deliveries/{did}/complete", headers=admin)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "delivered"


async def test_delivering_more_than_ordered_is_refused(client, admin, base, product):
    """The exactly-once guard: cumulative fulfilment can never exceed the order."""
    order = (await client.post("/api/v1/sales/orders", headers=admin, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [_line(product, base, "10")],
    })).json()
    oid = order["id"]

    d1 = (await client.post("/api/v1/sales/deliveries", headers=admin, json={
        "sale_order_id": oid, "lines": [{"sale_order_line_no": 1, "qty": "6"}]})).json()
    d2 = (await client.post("/api/v1/sales/deliveries", headers=admin, json={
        "sale_order_id": oid, "lines": [{"sale_order_line_no": 1, "qty": "6"}]})).json()

    ok = await client.post(f"/api/v1/sales/deliveries/{d1['id']}/dispatch", headers=admin)
    assert ok.status_code == 200, ok.text
    over = await client.post(f"/api/v1/sales/deliveries/{d2['id']}/dispatch", headers=admin)
    assert over.status_code == 409, "6 + 6 > 10 ordered"


async def test_deliver_full_convenience_endpoint(client, admin, base, product):
    order = (await client.post("/api/v1/sales/orders", headers=admin, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [_line(product, base, "15")],
    })).json()
    r = await client.post(f"/api/v1/sales/orders/{order['id']}/deliver", headers=admin, json={})
    assert r.status_code in (200, 201), r.text
    assert r.json()["status"] == "dispatched"


async def test_deliveries_are_listable(client, admin):
    r = await client.get("/api/v1/sales/deliveries", headers=admin)
    assert r.status_code == 200


# ---- billing an order -----------------------------------------------------
async def test_billing_after_delivery_moves_no_further_stock(client, admin, base, product):
    """Decision #5: the delivery already moved the goods, so the invoice must
    move nothing — this is the double-count that would be invisible in money."""
    order = (await client.post("/api/v1/sales/orders", headers=admin, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [_line(product, base, "20")],
    })).json()
    await client.post(f"/api/v1/sales/orders/{order['id']}/deliver", headers=admin, json={})
    on_hand_after_delivery, _, _ = await _balance(client, admin, product)

    bill = await client.post(f"/api/v1/sales/orders/{order['id']}/bill", headers=admin, json={})
    assert bill.status_code in (200, 201), bill.text
    assert bill.json()["lines"][0]["moved_qty"] == "0.000000", "the bill must not move again"

    on_hand_after_bill, _, _ = await _balance(client, admin, product)
    assert on_hand_after_bill == on_hand_after_delivery


async def test_billing_without_delivery_makes_the_bill_the_mover(client, admin, base, product):
    order = (await client.post("/api/v1/sales/orders", headers=admin, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [_line(product, base, "20")],
    })).json()
    before, _, _ = await _balance(client, admin, product)

    bill = await client.post(f"/api/v1/sales/orders/{order['id']}/bill", headers=admin, json={})
    assert bill.status_code in (200, 201), bill.text
    assert bill.json()["lines"][0]["moved_qty"] == "20.000000"
    after, reserved, _ = await _balance(client, admin, product)
    assert float(after) == pytest.approx(float(before) - 20)
    assert reserved == "0.000000"


async def test_a_bill_charges_what_the_order_quoted(client, admin, base, product):
    """The V2.6 mispricing: billing re-derived GST from the product and dropped
    the order line's discount, so a quote of 383.00 invoiced 365.00."""
    order = (await client.post("/api/v1/sales/orders", headers=admin, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [_line(product, base, "10", "100", discount_pct="5")],
    })).json()
    quoted = order["grand_total"]

    bill = await client.post(f"/api/v1/sales/orders/{order['id']}/bill", headers=admin, json={})
    assert bill.json()["grand_total"] == quoted, "the invoice must honour the quote"


# ---- counter sale ---------------------------------------------------------
async def test_counter_sale_posts_without_an_order(client, admin, base, product, idem):
    before, _, _ = await _balance(client, admin, product)
    r = await client.post("/api/v1/sales/bills", headers={**admin, **idem}, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [_line(product, base, "12", "100")],
        "paid_amount": "1260", "payment_account_id": base["account"],
    })
    assert r.status_code in (200, 201), r.text
    bill = r.json()
    assert bill["grand_total"] == "1260.00"
    assert bill["balance_amount"] == "0.00", "paid in full at the counter"

    after, _, _ = await _balance(client, admin, product)
    assert float(after) == pytest.approx(float(before) - 12), "the bill is the sole mover"


async def test_counter_sale_needs_a_known_customer(client, admin, base, product, idem):
    r = await client.post("/api/v1/sales/bills", headers={**admin, **idem}, json={
        "customer_id": 999999, "branch_id": base["branch"],
        "lines": [_line(product, base)],
    })
    assert r.status_code == 422, r.text


async def test_selling_more_than_exists_is_409(client, admin, base, product, idem):
    r = await client.post("/api/v1/sales/bills", headers={**admin, **idem}, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [_line(product, base, "999999")],
    })
    assert r.status_code == 409, r.text


async def test_bills_list_and_payment_history(client, admin, base, product, idem):
    posted = await client.post("/api/v1/sales/bills", headers={**admin, **idem}, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [_line(product, base, "5", "100")],
        "paid_amount": "200", "payment_account_id": base["account"],
    })
    bid = posted.json()["id"]

    listed = await client.get("/api/v1/sales/bills", headers=admin,
                              params={"branch_id": base["branch"]})
    assert listed.status_code == 200 and any(b["id"] == bid for b in listed.json())

    pays = await client.get(f"/api/v1/sales/bills/{bid}/payments", headers=admin)
    assert pays.status_code == 200 and pays.json()


# ---- returns --------------------------------------------------------------
async def test_sales_return_brings_goods_back_and_credits_the_customer(
    client, admin, base, product, idem
):
    before, _, _ = await _balance(client, admin, product)
    r = await client.post("/api/v1/sales/returns", headers={**admin, **idem}, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "godown_id": base["godown"], "lines": [_line(product, base, "4", "100")],
    })
    assert r.status_code in (200, 201), r.text
    assert r.json()["grand_total"] == "420.00"
    after, _, _ = await _balance(client, admin, product)
    assert float(after) == pytest.approx(float(before) + 4)


async def test_returns_are_listable(client, admin, base):
    r = await client.get("/api/v1/sales/returns", headers=admin,
                         params={"branch_id": base["branch"]})
    assert r.status_code == 200


# ---- amendment ------------------------------------------------------------
async def test_cancelling_a_sales_bill_puts_the_goods_back(client, admin, base, product, idem):
    posted = await client.post("/api/v1/sales/bills", headers={**admin, **idem}, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [_line(product, base, "8", "100")],
    })
    bill = posted.json()
    after_bill, _, _ = await _balance(client, admin, product)

    r = await client.post(f"/api/v1/sales/bills/{bill['id']}/cancel", headers=admin,
                          json={"reason": "customer walked out"})
    assert r.status_code == 200, r.text
    after_cancel, _, _ = await _balance(client, admin, product)
    assert float(after_cancel) == pytest.approx(float(after_bill) + 8)


async def test_amending_a_sales_bill_supersedes_it(client, admin, base, product, idem):
    posted = await client.post("/api/v1/sales/bills", headers={**admin, **idem}, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [_line(product, base, "5", "100")],
    })
    old = posted.json()
    r = await client.put(f"/api/v1/sales/bills/{old['id']}", headers=admin, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [_line(product, base, "7", "100")], "reason": "wrong quantity",
    })
    assert r.status_code == 200, r.text
    assert r.json()["id"] != old["id"]
    assert r.json()["grand_total"] == "735.00"  # 7 x 100 + 5%
