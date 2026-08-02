"""Reports, dashboard, money preview, printing and the activity feed."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

TODAY = "2026-01-01"
END = "2026-12-31"


# ---- money preview --------------------------------------------------------
async def test_money_preview_matches_the_posting_engine(client, admin):
    """The screens render this instead of doing the arithmetic in TypeScript,
    so it must agree with what posting would compute, to the paisa."""
    r = await client.post("/api/v1/money/preview", headers=admin, json={
        "lines": [{"qty": "10", "rate": "100", "gst_rate": "5"}],
    })
    assert r.status_code == 200, r.text
    t = r.json()["totals"]
    assert t["taxable_total"] == "1000.00"
    assert t["cgst_total"] == "25.00" and t["sgst_total"] == "25.00"
    assert t["igst_total"] == "0.00"
    assert t["grand_total"] == "1050.00"
    # every money field is a STRING with scale — a float renders 1050 not 1050.00
    assert all(isinstance(v, str) and "." in v for v in t.values())


async def test_money_preview_line_fields_all_carry_scale(client, admin):
    r = await client.post("/api/v1/money/preview", headers=admin, json={
        "lines": [{"qty": "10", "rate": "30", "gst_rate": "5"}],
    })
    line = r.json()["lines"][0]
    for field in ("gross", "discount", "header_discount_alloc", "taxable",
                  "cgst", "sgst", "igst", "tax", "line_total"):
        assert "." in line[field], f"{field} lost its scale: {line[field]}"


async def test_money_preview_spreads_the_overall_discount_before_tax(client, admin):
    """A post-tax lump sum would overstate every line's GST and break §6."""
    r = await client.post("/api/v1/money/preview", headers=admin, json={
        "discount_amount": "100",
        "lines": [{"qty": "10", "rate": "50", "gst_rate": "10"},
                  {"qty": "10", "rate": "50", "gst_rate": "10"}],
    })
    t = r.json()["totals"]
    assert t["taxable_total"] == "900.00", "1000 less the 100 overall discount"
    assert t["tax_total"] == "90.00", "tax is on the DISCOUNTED taxable"
    allocs = [line["header_discount_alloc"] for line in r.json()["lines"]]
    assert allocs == ["50.00", "50.00"], "spread pro-rata across the lines"


async def test_money_preview_with_no_lines_is_empty_not_an_error(client, admin):
    r = await client.post("/api/v1/money/preview", headers=admin, json={"lines": []})
    assert r.status_code == 200
    assert r.json()["totals"] is None


async def test_a_discount_bigger_than_the_invoice_is_refused(client, admin):
    r = await client.post("/api/v1/money/preview", headers=admin, json={
        "discount_amount": "99999",
        "lines": [{"qty": "1", "rate": "10", "gst_rate": "0"}],
    })
    assert r.status_code == 422


# ---- dashboard ------------------------------------------------------------
MONEY_WIDGETS = ("today_sales", "today_purchase", "today_collection", "today_expenses",
                 "current_stock_value", "outstanding_receivable", "outstanding_payable",
                 "petty_cash")


async def test_dashboard_returns_its_widgets(client, admin, base):
    r = await client.get("/api/v1/dashboard", headers=admin,
                         params={"branch_id": base["branch"]})
    assert r.status_code == 200, r.text
    body = r.json()
    for key in MONEY_WIDGETS + ("today_orders", "pending_deliveries", "low_stock",
                                "top_selling", "recent_activities"):
        assert key in body, f"dashboard is missing {key}"
    assert isinstance(body["today_orders"], int), "a count is a number"


async def test_dashboard_answers_the_same_shape_cached_and_uncached(client, admin, base):
    """The cache round-trips through json.dumps(default=str), so a Decimal came
    back as "0" from Redis but 0.0 from the live path — the SAME field changed
    type when the 30s TTL lapsed. Nothing is more painful to reproduce by hand.
    """
    url, params = "/api/v1/dashboard", {"branch_id": base["branch"]}
    first = (await client.get(url, headers=admin, params=params)).json()
    second = (await client.get(url, headers=admin, params=params)).json()
    assert second["cached"] is True, "the second read must come from Redis"

    for key in MONEY_WIDGETS:
        assert isinstance(first[key], str), f"{key} is {type(first[key]).__name__}, want str"
        assert type(first[key]) is type(second[key]), (
            f"{key} changes type when cached: "
            f"{first[key]!r} -> {second[key]!r}"
        )
    assert {k: v for k, v in first.items() if k != "cached"} == \
           {k: v for k, v in second.items() if k != "cached"}


# ---- reports --------------------------------------------------------------
async def test_report_catalogue_is_served(client, admin):
    r = await client.get("/api/v1/reports", headers=admin)
    assert r.status_code == 200
    rows = r.json()
    rows = rows if isinstance(rows, list) else rows.get("reports", [])
    assert len(rows) == 48, f"v2 §6 specifies 48 reports, got {len(rows)}"


async def test_every_report_runs(client, admin):
    """All 48, driven for real. They read what earlier phases wrote, so a
    schema change in any module surfaces here first."""
    catalogue = (await client.get("/api/v1/reports", headers=admin)).json()
    rows = catalogue if isinstance(catalogue, list) else catalogue.get("reports", [])
    failures = []
    for entry in rows:
        key = entry["key"]
        r = await client.get(f"/api/v1/reports/{key}", headers=admin,
                             params={"date_from": TODAY, "date_to": END})
        if r.status_code != 200:
            failures.append(f"{key} -> {r.status_code} {r.text[:120]}")
            continue
        body = r.json()
        assert "rows" in body and "summary" in body, f"{key} has the wrong shape"
    assert not failures, "reports failed:\n" + "\n".join(failures)


async def test_an_unknown_report_is_404(client, admin):
    r = await client.get("/api/v1/reports/not-a-report", headers=admin,
                         params={"date_from": TODAY, "date_to": END})
    assert r.status_code == 404


async def test_reports_count_only_posted_documents(client, admin, base, idem):
    """The cross-cutting rule: an amendment leaves the cancelled original AND
    its replacement in the table, so without status='posted' every amended
    invoice double-counts. Proven by cancelling one and watching the total.
    """
    product = (await client.post("/api/v1/products", headers=admin, json={
        "name": "ReportBait", "base_unit_id": base["unit"], "gst_rate": "0",
        "sale_price": "100"})).json()["id"]
    await client.post("/api/v1/stock/adjustments", headers={**admin, **idem}, json={
        "branch_id": base["branch"], "godown_id": base["godown"], "adj_reason": "opening",
        "lines": [{"product_id": product, "entered_qty": "100",
                   "entered_unit_id": base["unit"], "unit_cost": "10"}]})

    async def sales_total() -> float:
        r = await client.get("/api/v1/reports/sales_summary", headers=admin,
                             params={"date_from": TODAY, "date_to": END})
        assert r.status_code == 200, r.text
        return float(r.json()["summary"].get("total") or 0)

    before = await sales_total()
    bill = (await client.post("/api/v1/sales/bills",
                              headers={**admin, "Idempotency-Key": "report-bait"}, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [{"product_id": product, "godown_id": base["godown"], "entered_qty": "10",
                   "entered_unit_id": base["unit"], "rate": "100", "gst_rate": "0"}],
    })).json()
    assert await sales_total() == pytest.approx(before + 1000)

    cancelled = await client.post(f"/api/v1/sales/bills/{bill['id']}/cancel",
                                  headers=admin, json={"reason": "test"})
    assert cancelled.status_code == 200, cancelled.text
    assert await sales_total() == pytest.approx(before), (
        "a cancelled invoice must leave the report entirely"
    )


# ---- printing -------------------------------------------------------------
async def test_print_payload_is_assembled_for_a_sales_bill(client, admin, base, idem):
    product = (await client.post("/api/v1/products", headers=admin, json={
        "name": "PrintMe", "base_unit_id": base["unit"], "gst_rate": "5",
        "sale_price": "100",
    })).json()["id"]
    await client.post("/api/v1/stock/adjustments", headers={**admin, **idem}, json={
        "branch_id": base["branch"], "godown_id": base["godown"], "adj_reason": "opening",
        "lines": [{"product_id": product, "entered_qty": "20",
                   "entered_unit_id": base["unit"], "unit_cost": "50"}]})
    bill = (await client.post("/api/v1/sales/bills",
                              headers={**admin, "Idempotency-Key": "print-me-once"}, json={
        "customer_id": base["customer"], "branch_id": base["branch"],
        "lines": [{"product_id": product, "godown_id": base["godown"], "entered_qty": "3",
                   "entered_unit_id": base["unit"], "rate": "100", "gst_rate": "5"}],
    })).json()

    r = await client.get(f"/api/v1/print/sales_bill/{bill['id']}", headers=admin)
    assert r.status_code == 200, r.text
    payload = r.json()
    # ONE payload drives 58mm, 80mm, A5 and A4 — the browser only lays it out
    for key in ("document", "org", "branch", "party", "lines", "totals"):
        assert key in payload, f"print payload is missing {key}"
    assert payload["lines"], "an invoice prints its lines"
    assert "amount_in_words" in payload or "amount_in_words" in payload.get("totals", {})


async def test_printing_an_unknown_document_is_404(client, admin):
    r = await client.get("/api/v1/print/sales_bill/99999999", headers=admin)
    assert r.status_code == 404


async def test_an_unknown_print_doc_type_is_refused(client, admin):
    r = await client.get("/api/v1/print/not_a_doc/1", headers=admin)
    assert r.status_code in (404, 422)


# ---- activity feed --------------------------------------------------------
async def test_activity_feed_is_served(client, admin):
    """Projected from the outbox by Celery; the endpoint must answer even when
    the worker has not drained anything yet."""
    r = await client.get("/api/v1/activity", headers=admin)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["items"], list)
    assert body["count"] == len(body["items"])
