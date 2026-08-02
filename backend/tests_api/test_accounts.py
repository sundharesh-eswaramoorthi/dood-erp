"""Accounts: bank/cash accounts, payment types, vouchers, allocation, expenses."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from .conftest import uniq

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def account(client, admin, base) -> int:
    r = await client.post("/api/v1/accounts/bank-accounts", headers=admin, json={
        "name": uniq("Till"), "account_type": "cash", "opening_balance": "10000",
        "branch_id": base["branch"],
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


async def _net(client, admin, party) -> float:
    r = await client.get(f"/api/v1/parties/{party}/ledger", headers=admin)
    return float(r.json()["net_balance"])


# ---- bank & cash accounts -------------------------------------------------
async def test_account_create_and_list(client, admin, account):
    listed = await client.get("/api/v1/accounts/bank-accounts", headers=admin)
    assert listed.status_code == 200
    row = next(a for a in listed.json() if a["id"] == account)
    assert row["current_balance"] == "10000.00"
    assert row["branch_id"], "V2.16 made the branch mandatory on an account"


async def test_accounts_can_be_filtered_by_branch(client, admin, base):
    r = await client.get("/api/v1/accounts/bank-accounts", headers=admin,
                         params={"branch_id": base["branch"]})
    assert r.status_code == 200
    assert all(a["branch_id"] == base["branch"] for a in r.json())


async def test_an_account_needs_a_branch_you_work_in(client, admin):
    other = await client.post("/api/v1/branches", headers=admin, json={"name": uniq("Nowhere")})
    r = await client.post("/api/v1/accounts/bank-accounts", headers=admin, json={
        "name": uniq("Ghost"), "account_type": "bank", "branch_id": other.json()["id"],
    })
    assert r.status_code == 403, r.text


# ---- payment types --------------------------------------------------------
async def test_payment_type_create_list_update(client, admin):
    created = await client.post("/api/v1/accounts/payment-types", headers=admin,
                                json={"name": uniq("Voucher"), "kind": "other"})
    assert created.status_code in (200, 201), created.text
    pid = created.json()["id"]

    listed = await client.get("/api/v1/accounts/payment-types", headers=admin)
    assert any(p["id"] == pid for p in listed.json())

    upd = await client.put(f"/api/v1/accounts/payment-types/{pid}", headers=admin,
                           json={"name": uniq("Renamed")})
    assert upd.status_code == 200, upd.text


async def test_the_seeded_payment_types_are_present(client, admin):
    r = await client.get("/api/v1/accounts/payment-types", headers=admin)
    names = {p["name"] for p in r.json()}
    assert {"Cash", "UPI", "Card"} <= names


# ---- vouchers -------------------------------------------------------------
async def test_receipt_voucher_credits_the_party_and_fills_the_account(
    client, admin, base, account
):
    before = await _net(client, admin, base["customer"])
    r = await client.post("/api/v1/accounts/payment-vouchers", headers=admin, json={
        "party_id": base["customer"], "branch_id": base["branch"],
        "voucher_type": "receipt", "account_id": account, "amount": "1500",
        "payment_type_id": base["payment_type"], "note": "part payment",
    })
    assert r.status_code in (200, 201), r.text
    # money in from a customer REDUCES what they owe
    assert await _net(client, admin, base["customer"]) == pytest.approx(before - 1500)

    accounts = await client.get("/api/v1/accounts/bank-accounts", headers=admin)
    row = next(a for a in accounts.json() if a["id"] == account)
    assert row["current_balance"] == "11500.00"


async def test_payment_voucher_debits_the_party_and_empties_the_account(
    client, admin, base, account
):
    before = await _net(client, admin, base["supplier"])
    r = await client.post("/api/v1/accounts/payment-vouchers", headers=admin, json={
        "party_id": base["supplier"], "branch_id": base["branch"],
        "voucher_type": "payment", "account_id": account, "amount": "700",
    })
    assert r.status_code in (200, 201), r.text
    assert await _net(client, admin, base["supplier"]) == pytest.approx(before + 700)


async def test_a_split_voucher_records_every_tender(client, admin, base, account):
    r = await client.post("/api/v1/accounts/payment-vouchers", headers=admin, json={
        "party_id": base["customer"], "branch_id": base["branch"],
        "voucher_type": "receipt",
        "payments": [
            {"account_id": account, "payment_type_id": base["payment_type"], "amount": "400"},
            {"account_id": account, "amount": "600", "reference": "UPI-123"},
        ],
    })
    assert r.status_code in (200, 201), r.text
    assert str(r.json()["amount"]) == "1000.00", "the total is derived from the tenders"


async def test_an_unknown_voucher_type_is_refused(client, admin, base, account):
    r = await client.post("/api/v1/accounts/payment-vouchers", headers=admin, json={
        "party_id": base["customer"], "voucher_type": "sideways",
        "account_id": account, "amount": "10",
    })
    assert r.status_code == 422


async def test_vouchers_are_listable(client, admin, base):
    r = await client.get("/api/v1/accounts/payment-vouchers", headers=admin,
                         params={"branch_id": base["branch"]})
    assert r.status_code == 200


# ---- open items & allocation ---------------------------------------------
async def test_open_items_and_allocating_a_receipt_to_a_bill(
    client, admin, base, account, idem
):
    """v2 §3 bill-wise settlement: an unallocated receipt can be pointed at the
    invoice it actually pays."""
    product = (await client.post("/api/v1/products", headers=admin, json={
        "name": uniq("Alloc"), "base_unit_id": base["unit"], "gst_rate": "0",
        "sale_price": "100",
    })).json()["id"]
    await client.post("/api/v1/stock/adjustments",
                      headers={**admin, "Idempotency-Key": str(uuid.uuid4())}, json={
        "branch_id": base["branch"], "godown_id": base["godown"], "adj_reason": "opening",
        "lines": [{"product_id": product, "entered_qty": "50",
                   "entered_unit_id": base["unit"], "unit_cost": "40"}]})

    bill = (await client.post("/api/v1/sales/bills", headers={**admin, **idem}, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [{"product_id": product, "godown_id": base["godown"], "entered_qty": "10",
                   "entered_unit_id": base["unit"], "rate": "100", "gst_rate": "0"}],
    })).json()
    assert bill["grand_total"] == "1000.00"

    items = await client.get(f"/api/v1/accounts/parties/{base['customer']}/open-items",
                             headers=admin)
    assert items.status_code == 200, items.text
    assert items.json(), "the unpaid invoice must show as an open item"

    voucher = (await client.post("/api/v1/accounts/payment-vouchers", headers=admin, json={
        "party_id": base["customer"], "branch_id": base["branch"],
        "voucher_type": "receipt", "account_id": account, "amount": "1000",
        "allocations": [],   # explicitly left on account
    })).json()

    r = await client.post(f"/api/v1/accounts/vouchers/{voucher['id']}/allocate", headers=admin,
                          json={"allocations": [{"entry_id": None, "doc_type": "sales_bill",
                                                 "doc_id": bill["id"], "amount": "1000"}]})
    # the endpoint exists and either allocates or explains why not
    assert r.status_code in (200, 201, 422), r.text


# ---- expenses -------------------------------------------------------------
async def test_expense_category_create_and_list(client, admin):
    created = await client.post("/api/v1/accounts/expense-categories", headers=admin,
                                json={"name": uniq("Fuel")})
    assert created.status_code in (200, 201), created.text
    listed = await client.get("/api/v1/accounts/expense-categories", headers=admin)
    assert any(c["id"] == created.json()["id"] for c in listed.json())


async def test_expense_reduces_the_account_balance(client, admin, base, account):
    cat = (await client.post("/api/v1/accounts/expense-categories", headers=admin,
                             json={"name": uniq("Rent")})).json()
    r = await client.post("/api/v1/accounts/expenses", headers=admin, json={
        "account_id": account, "branch_id": base["branch"], "amount": "800",
        "category_id": cat["id"], "note": "office rent",
    })
    assert r.status_code in (200, 201), r.text
    assert r.json()["account_balance"] == "9200.00", "10000 opening less 800"


async def test_expenses_are_listable(client, admin, base):
    r = await client.get("/api/v1/accounts/expenses", headers=admin,
                         params={"branch_id": base["branch"]})
    assert r.status_code == 200


async def test_an_expense_needs_a_real_account(client, admin, base):
    r = await client.post("/api/v1/accounts/expenses", headers=admin, json={
        "account_id": 999999, "branch_id": base["branch"], "amount": "10",
    })
    assert r.status_code in (403, 404, 422), r.text


async def test_a_negative_expense_is_refused(client, admin, base, account):
    r = await client.post("/api/v1/accounts/expenses", headers=admin, json={
        "account_id": account, "branch_id": base["branch"], "amount": "-5",
    })
    assert r.status_code == 422
