"""Parties, their sub-resources and their ledger."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from .conftest import uniq

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def party(client, admin, base) -> int:
    r = await client.post("/api/v1/parties", headers={**admin, "Idempotency-Key": str(uuid.uuid4())},
                          json={"name": uniq("Party"), "area": "North",
                                "serving_branch_id": base["branch"], "phone": "9012345678"})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# ---- create / read / update ----------------------------------------------
async def test_party_create_assigns_a_code_and_is_readable(client, admin, base):
    r = await client.post("/api/v1/parties", headers={**admin, "Idempotency-Key": str(uuid.uuid4())},
                          json={"name": uniq("Acme"), "area": "South",
                                "serving_branch_id": base["branch"],
                                "gstin": "33ABCDE1234F1Z5", "credit_limit": "50000"})
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["party_code"], "the numbering series must allocate a code"

    got = await client.get(f"/api/v1/parties/{body['id']}", headers=admin)
    assert got.status_code == 200
    assert got.json()["name"] == body["name"]


async def test_party_requires_a_branch_it_can_reach(client, admin):
    """V2.16: the branch that serves a party is the branch that can see it, so
    it is mandatory and must be one the caller works in."""
    missing = await client.post("/api/v1/parties",
                                headers={**admin, "Idempotency-Key": str(uuid.uuid4())},
                                json={"name": uniq("NoBranch"), "area": "X"})
    assert missing.status_code == 422, missing.text

    bogus = await client.post("/api/v1/parties",
                              headers={**admin, "Idempotency-Key": str(uuid.uuid4())},
                              json={"name": uniq("Bogus"), "area": "X",
                                    "serving_branch_id": 999999})
    assert bogus.status_code in (403, 422), bogus.text


async def test_party_update_returns_the_stored_row(client, admin, party):
    upd = await client.put(f"/api/v1/parties/{party}", headers=admin,
                           json={"area": "  Renamed Area  ", "credit_limit": "12345"})
    assert upd.status_code == 200, upd.text
    assert upd.json()["area"] == "Renamed Area", "area is trimmed on the way in"
    fresh = await client.get(f"/api/v1/parties/{party}", headers=admin)
    assert upd.json()["credit_limit"] == fresh.json()["credit_limit"]


async def test_unknown_party_is_404(client, admin):
    r = await client.get("/api/v1/parties/99999999", headers=admin)
    assert r.status_code == 404


async def test_party_list_search_and_areas(client, admin, party):
    listed = await client.get("/api/v1/parties", headers=admin)
    assert listed.status_code == 200
    row = next(p for p in listed.json() if p["id"] == party)
    # the list joins the balances so the screen need not fetch per row
    assert "receivable" in row and "payable" in row

    areas = await client.get("/api/v1/parties/areas", headers=admin)
    assert areas.status_code == 200
    assert "North" in areas.json()

    none = await client.get("/api/v1/parties", headers=admin, params={"q": "zzz-nothing"})
    assert none.status_code == 200 and none.json() == []


async def test_idempotency_key_replays_rather_than_duplicating(client, admin, base):
    """Two clicks on Save must not make two customers."""
    key = {"Idempotency-Key": str(uuid.uuid4())}
    payload = {"name": uniq("Doubled"), "area": "East", "serving_branch_id": base["branch"]}
    first = await client.post("/api/v1/parties", headers={**admin, **key}, json=payload)
    second = await client.post("/api/v1/parties", headers={**admin, **key}, json=payload)
    assert first.status_code in (200, 201) and second.status_code in (200, 201)
    assert first.json()["id"] == second.json()["id"], "the replay must return the same row"


# ---- sub-resources --------------------------------------------------------
async def test_contacts_addresses_documents_and_gstins(client, admin, party):
    c = await client.post(f"/api/v1/parties/{party}/contacts", headers=admin,
                          json={"name": "Ravi", "phone": "9800000000",
                                "relationship": "owner", "is_primary": True})
    assert c.status_code in (200, 201), c.text
    assert any(x["name"] == "Ravi" for x in
               (await client.get(f"/api/v1/parties/{party}/contacts", headers=admin)).json())

    a = await client.post(f"/api/v1/parties/{party}/addresses", headers=admin,
                          json={"label": "Shop", "line1": "12 Bazaar St", "city": "Erode",
                                "state": "TN", "pincode": "638001", "is_default": True})
    assert a.status_code in (200, 201), a.text
    assert (await client.get(f"/api/v1/parties/{party}/addresses", headers=admin)).json()

    d = await client.post(f"/api/v1/parties/{party}/documents", headers=admin,
                          json={"doc_type": "PAN", "file_name": "pan.pdf",
                                "storage_key": "s3://bucket/pan.pdf",
                                "content_type": "application/pdf"})
    assert d.status_code in (200, 201), d.text
    assert (await client.get(f"/api/v1/parties/{party}/documents", headers=admin)).json()

    g = await client.post(f"/api/v1/parties/{party}/gst-registrations", headers=admin,
                          json={"gstin": "29ABCDE1234F1Z5", "state_code": "29",
                                "is_default": True})
    assert g.status_code in (200, 201), g.text
    # decision #2: ONE party may hold MANY GSTINs, one per state
    g2 = await client.post(f"/api/v1/parties/{party}/gst-registrations", headers=admin,
                           json={"gstin": "33ABCDE1234F1Z5", "state_code": "33"})
    assert g2.status_code in (200, 201), g2.text
    assert len((await client.get(f"/api/v1/parties/{party}/gst-registrations",
                                 headers=admin)).json()) >= 2


async def test_tags_can_be_attached_and_removed(client, admin, party):
    tag = await client.post("/api/v1/tags", headers=admin, json={"name": uniq("VIP")})
    tid = tag.json()["id"]

    attached = await client.post(f"/api/v1/parties/{party}/tags", headers=admin,
                                 json={"tag_id": tid})
    assert attached.status_code in (200, 201, 204), attached.text
    detail = await client.get(f"/api/v1/parties/{party}", headers=admin)
    assert any(t["id"] == tid for t in detail.json().get("tags", []))

    removed = await client.delete(f"/api/v1/parties/{party}/tags/{tid}", headers=admin)
    assert removed.status_code in (200, 204), removed.text
    detail2 = await client.get(f"/api/v1/parties/{party}", headers=admin)
    assert not any(t["id"] == tid for t in detail2.json().get("tags", []))


# ---- ledger ---------------------------------------------------------------
async def test_manual_ledger_entries_move_the_balance(client, admin, party):
    empty = await client.get(f"/api/v1/parties/{party}/ledger", headers=admin)
    assert empty.status_code == 200

    debit = await client.post(f"/api/v1/parties/{party}/ledger/entries", headers=admin,
                              json={"entry_side": "debit", "amount": "1000", "note": "opening"})
    assert debit.status_code in (200, 201), debit.text

    credit = await client.post(f"/api/v1/parties/{party}/ledger/entries", headers=admin,
                               json={"entry_side": "credit", "amount": "400"})
    assert credit.status_code in (200, 201), credit.text

    ledger = (await client.get(f"/api/v1/parties/{party}/ledger", headers=admin)).json()
    # net = debits - credits, and it is a decimal STRING not a float
    assert str(ledger["net_balance"]) == "600.00", ledger


async def test_a_bad_ledger_side_is_refused(client, admin, party):
    r = await client.post(f"/api/v1/parties/{party}/ledger/entries", headers=admin,
                          json={"entry_side": "sideways", "amount": "10"})
    assert r.status_code == 422


async def test_a_negative_ledger_amount_is_refused(client, admin, party):
    r = await client.post(f"/api/v1/parties/{party}/ledger/entries", headers=admin,
                          json={"entry_side": "debit", "amount": "-10"})
    assert r.status_code == 422


async def test_opening_balance_is_ledger_backed(client, admin, base):
    """V2.1: the opening figure is posted as a real ledger entry, so it shows in
    the balance rather than sitting in a column nothing reads."""
    r = await client.post("/api/v1/parties", headers={**admin, "Idempotency-Key": str(uuid.uuid4())},
                          json={"name": uniq("Opening"), "area": "West",
                                "serving_branch_id": base["branch"],
                                "opening_balance": "5000", "opening_balance_side": "receivable"})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    ledger = (await client.get(f"/api/v1/parties/{pid}/ledger", headers=admin)).json()
    assert str(ledger["net_balance"]) == "5000.00", ledger
