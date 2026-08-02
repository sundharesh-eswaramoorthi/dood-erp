"""Masters and settings: branches, godowns, units, products, tags, tax rates,
document types, numbering series, feature flags, print settings.

These are the endpoints the service tests never touch at all — every one of
them is reached only through a router.
"""
from __future__ import annotations

import pytest

from .conftest import uniq

pytestmark = pytest.mark.asyncio


# ---- branches -------------------------------------------------------------
async def test_branch_create_list_and_update(client, admin):
    created = await client.post("/api/v1/branches", headers=admin, json={
        "name": uniq("Branch"), "code": uniq("BR")[:8], "address": "Main Rd",
        "phone": "9876500000", "gstin": "33ABCDE1234F1Z5", "state_code": "33",
    })
    assert created.status_code in (200, 201), created.text
    bid = created.json()["id"]

    listed = await client.get("/api/v1/branches", headers=admin)
    assert listed.status_code == 200
    assert any(b["id"] == bid for b in listed.json())

    renamed = await client.put(f"/api/v1/branches/{bid}", headers=admin,
                               json={"phone": "9876511111"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["phone"] == "9876511111"


async def test_a_duplicate_branch_name_is_refused(client, admin):
    name = uniq("Twice")
    first = await client.post("/api/v1/branches", headers=admin, json={"name": name})
    assert first.status_code in (200, 201)
    second = await client.post("/api/v1/branches", headers=admin, json={"name": name})
    assert second.status_code in (409, 422), second.text


async def test_branch_name_is_required(client, admin):
    r = await client.post("/api/v1/branches", headers=admin, json={})
    assert r.status_code == 422


# ---- godowns --------------------------------------------------------------
async def test_godown_create_list_and_update(client, admin, base):
    created = await client.post("/api/v1/godowns", headers=admin, json={
        "name": uniq("Store"), "branch_id": base["branch"], "code": uniq("G")[:8],
    })
    assert created.status_code in (200, 201), created.text
    gid = created.json()["id"]

    listed = await client.get("/api/v1/godowns", headers=admin)
    assert any(g["id"] == gid for g in listed.json())

    updated = await client.put(f"/api/v1/godowns/{gid}", headers=admin,
                               json={"name": uniq("Renamed")})
    assert updated.status_code == 200, updated.text


async def test_godowns_can_be_listed_across_all_branches(client, admin):
    """The transfer destination picker needs every godown the caller can reach,
    not just the branch currently selected."""
    r = await client.get("/api/v1/godowns", headers=admin, params={"all_branches": True})
    assert r.status_code == 200
    assert all("branch_id" in g for g in r.json())


async def test_a_godown_holding_stock_cannot_be_deactivated(client, admin, base):
    """stock_balance is keyed on (branch, godown); deactivating a godown with
    goods in it would orphan the balance."""
    r = await client.put(f"/api/v1/godowns/{base['godown']}", headers=admin,
                         json={"is_active": False})
    assert r.status_code in (409, 422), f"expected a refusal, got {r.status_code} {r.text}"


# ---- units ----------------------------------------------------------------
async def test_unit_create_and_list(client, admin):
    code = uniq("U")[:8].upper()
    created = await client.post("/api/v1/units", headers=admin,
                                json={"code": code, "name": uniq("Unit")})
    assert created.status_code in (200, 201), created.text
    listed = await client.get("/api/v1/units", headers=admin)
    assert any(u["code"] == code for u in listed.json())


# ---- product categories & products ---------------------------------------
async def test_product_category_create_and_list(client, admin):
    created = await client.post("/api/v1/products/categories", headers=admin,
                                json={"name": uniq("Cat")})
    assert created.status_code in (200, 201), created.text
    listed = await client.get("/api/v1/products/categories", headers=admin)
    assert any(c["id"] == created.json()["id"] for c in listed.json())


async def test_product_create_get_update(client, admin, base):
    created = await client.post("/api/v1/products", headers=admin, json={
        "name": uniq("Widget"), "base_unit_id": base["unit"], "gst_rate": "12",
        "sale_price": "250", "purchase_price": "180", "hsn_code": "8419",
    })
    assert created.status_code in (200, 201), created.text
    pid = created.json()["id"]
    assert created.json()["code"], "a product must be auto-numbered when no code is given"

    got = await client.get(f"/api/v1/products/{pid}", headers=admin)
    assert got.status_code == 200
    assert got.json()["gst_rate"] == "12.00"

    upd = await client.put(f"/api/v1/products/{pid}", headers=admin,
                           json={"sale_price": "275"})
    assert upd.status_code == 200, upd.text
    # the UPDATE must answer with the STORED value, at the column's scale —
    # echoing the caller's "275" made the edit form and the list disagree
    fresh = await client.get(f"/api/v1/products/{pid}", headers=admin)
    assert upd.json()["sale_price"] == fresh.json()["sale_price"] == "275.0000"


async def test_product_list_reports_stock_and_filters(client, admin, base):
    r = await client.get("/api/v1/products", headers=admin,
                         params={"branch_id": base["branch"]})
    assert r.status_code == 200
    row = next(p for p in r.json() if p["id"] == base["product"])
    # the fixture posted an opening of 1000 @ 50 through the real adjustment path
    assert row["stock_qty"] == "1000.000000"
    assert row["avg_cost"] == "50.000000"
    assert row["units"], "line editors need the base unit plus every conversion"

    q = await client.get("/api/v1/products", headers=admin, params={"q": "zzz-no-such"})
    assert q.status_code == 200 and q.json() == []


async def test_unknown_product_is_404(client, admin):
    r = await client.get("/api/v1/products/99999999", headers=admin)
    assert r.status_code == 404


async def test_a_product_needs_a_base_unit(client, admin):
    r = await client.post("/api/v1/products", headers=admin, json={"name": uniq("NoUnit")})
    assert r.status_code == 422


# ---- tags & tax rates -----------------------------------------------------
async def test_tag_create_and_list(client, admin):
    created = await client.post("/api/v1/tags", headers=admin,
                                json={"name": uniq("Tag"), "color": "#ff0000"})
    assert created.status_code in (200, 201), created.text
    listed = await client.get("/api/v1/tags", headers=admin)
    assert any(t["id"] == created.json()["id"] for t in listed.json())


async def test_tax_rate_create_and_list(client, admin):
    created = await client.post("/api/v1/tax-rates", headers=admin,
                                json={"name": uniq("GST"), "rate": "18"})
    assert created.status_code in (200, 201), created.text
    listed = await client.get("/api/v1/tax-rates", headers=admin)
    assert any(t["id"] == created.json()["id"] for t in listed.json())


# ---- document types -------------------------------------------------------
async def test_document_type_create_list_update(client, admin):
    created = await client.post("/api/v1/document-types", headers=admin, json={
        "name": uniq("Doc"), "applies_to": "party", "is_required": False,
    })
    assert created.status_code in (200, 201), created.text
    did = created.json()["id"]
    listed = await client.get("/api/v1/document-types", headers=admin)
    assert any(d["id"] == did for d in listed.json())
    upd = await client.put(f"/api/v1/document-types/{did}", headers=admin,
                           json={"is_required": True})
    assert upd.status_code == 200, upd.text


# ---- numbering series -----------------------------------------------------
async def test_numbering_series_list_and_edit(client, admin):
    listed = await client.get("/api/v1/numbering-series", headers=admin)
    assert listed.status_code == 200
    series = listed.json()
    assert series, "a fresh install seeds a series per document type"
    target = next(s for s in series if s["doc_type"] == "party")
    upd = await client.put(f"/api/v1/numbering-series/{target['id']}", headers=admin,
                           json={"prefix": "CU-", "pad_width": 5})
    assert upd.status_code == 200, upd.text
    assert upd.json()["prefix"] == "CU-"


# ---- settings & feature flags --------------------------------------------
async def test_settings_read_and_write(client, admin):
    listed = await client.get("/api/v1/settings", headers=admin)
    assert listed.status_code == 200

    upd = await client.put("/api/v1/settings/purchase.po_tolerance_pct", headers=admin,
                           json={"value": {"pct": 15}})
    assert upd.status_code == 200, upd.text

    again = await client.get("/api/v1/settings", headers=admin)
    row = next(s for s in again.json() if s["key"] == "purchase.po_tolerance_pct")
    assert row["value"] == {"pct": 15}


async def test_feature_flags_are_listed(client, admin):
    r = await client.get("/api/v1/feature-flags", headers=admin)
    assert r.status_code == 200
    # a flat {name: bool} map, not a list of rows
    flags = r.json()
    assert isinstance(flags, dict)
    assert {"purchase_order", "sale_order"} <= set(flags)
    assert all(isinstance(v, bool) for v in flags.values())


# ---- print settings -------------------------------------------------------
async def test_print_settings_read_and_write(client, admin):
    got = await client.get("/api/v1/print/settings", headers=admin)
    assert got.status_code == 200

    upd = await client.put("/api/v1/print/settings", headers=admin,
                           json={"default_format": "a5", "footer_text": "Thank you"})
    assert upd.status_code == 200, upd.text

    again = await client.get("/api/v1/print/settings", headers=admin)
    assert again.json()["default_format"] == "a5"
