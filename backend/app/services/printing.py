"""Assemble a document for printing (v2 §9 "Termal print" / "Regular print").

The server builds the whole payload — org, branch, party, lines, tax summary,
amount in words, payment history — and the browser lays it out. Keeping the
figures here means a printed invoice and the posted document cannot disagree,
and the same payload drives a 58mm till roll and an A4 sheet.

The branch identity fields (code, address, GSTIN, state code) were added in
V2.4 precisely so this header would have something to print.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal

ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
        "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
        "Eighteen", "Nineteen"]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _under_thousand(n: int) -> str:
    if n < 20:
        return ONES[n]
    if n < 100:
        return (TENS[n // 10] + (" " + ONES[n % 10] if n % 10 else "")).strip()
    return (ONES[n // 100] + " Hundred" + (" " + _under_thousand(n % 100) if n % 100 else "")).strip()


def amount_in_words(amount: Decimal) -> str:
    """Indian numbering — lakh and crore, not million.

    An Indian invoice is expected to carry the amount in words, and getting the
    grouping wrong (1,234,567 vs 12,34,567) is immediately visible to whoever
    receives it.
    """
    amount = Decimal(amount)
    negative = amount < 0
    amount = abs(amount)
    rupees = int(amount)
    paise = int((amount - rupees) * 100 + Decimal("0.5"))
    if paise == 100:          # rounding carried
        rupees, paise = rupees + 1, 0

    if rupees == 0:
        words = "Zero"
    else:
        parts: list[str] = []
        crore, rupees_rem = divmod(rupees, 10_000_000)
        lakh, rupees_rem = divmod(rupees_rem, 100_000)
        thousand, rupees_rem = divmod(rupees_rem, 1_000)
        if crore:
            parts.append(f"{_under_thousand(crore) if crore < 1000 else amount_in_words(crore)} Crore")
        if lakh:
            parts.append(f"{_under_thousand(lakh)} Lakh")
        if thousand:
            parts.append(f"{_under_thousand(thousand)} Thousand")
        if rupees_rem:
            parts.append(_under_thousand(rupees_rem))
        words = " ".join(parts)

    out = f"{'Minus ' if negative else ''}Rupees {words}"
    if paise:
        out += f" and {_under_thousand(paise)} Paise"
    return out + " Only"


DOC_META = {
    "sales_bill": {
        "title": "TAX INVOICE", "line_table": "sales_bill_line", "line_fk": "bill_id",
        "party_col": "customer_id", "date_col": "bill_date", "party_label": "Bill To",
    },
    "purchase_bill": {
        "title": "PURCHASE BILL", "line_table": "purchase_bill_line", "line_fk": "bill_id",
        "party_col": "supplier_id", "date_col": "bill_date", "party_label": "Supplier",
    },
    "sales_return": {
        "title": "CREDIT NOTE", "line_table": "sales_return_line", "line_fk": "return_id",
        "party_col": "customer_id", "date_col": "return_date", "party_label": "Bill To",
    },
    "purchase_return": {
        "title": "DEBIT NOTE", "line_table": "purchase_return_line", "line_fk": "return_id",
        "party_col": "supplier_id", "date_col": "return_date", "party_label": "Supplier",
    },
}

# Defaults for the v2 §9 print settings; overridden per org via system_setting.
PRINT_DEFAULTS = {
    "default_format": "a4",      # a4 | a5 | thermal80 | thermal58
    "show_hsn": True,
    "show_tax_summary": True,
    "show_amount_in_words": True,
    "show_bank_details": False,
    "footer_text": "",
    "terms": "",
}


def _s(v):
    return str(v) if isinstance(v, Decimal) else v


async def print_settings(session: AsyncSession, org_id: int) -> dict:
    rows = (
        await session.execute(
            text("SELECT key, value FROM system_setting WHERE org_id=:o AND key LIKE 'print.%'"),
            {"o": org_id},
        )
    ).mappings().all()
    out = dict(PRINT_DEFAULTS)
    for r in rows:
        name = r["key"].removeprefix("print.")
        value = r["value"]
        out[name] = value.get("value", value) if isinstance(value, dict) else value
    return out


async def build_document(
    session: AsyncSession, principal: Principal, doc_type: str, doc_id: int
) -> dict:
    meta = DOC_META.get(doc_type)
    if meta is None:
        raise ValueError(f"{doc_type} cannot be printed")

    hdr = (
        await session.execute(text(f"SELECT * FROM {doc_type} WHERE id=:i"), {"i": doc_id})
    ).mappings().one_or_none()
    if hdr is None:
        raise LookupError(f"{doc_type} {doc_id} not found")

    org = (
        await session.execute(
            text("SELECT name FROM organization WHERE id=:o"), {"o": principal.org_id}
        )
    ).mappings().one()
    branch = (
        await session.execute(
            text("SELECT name, code, address, phone, gstin, state_code FROM branch WHERE id=:b"),
            {"b": hdr["branch_id"]},
        )
    ).mappings().one_or_none()
    party = (
        await session.execute(
            text("SELECT party_code, name, area, phone, gstin, pan FROM party WHERE id=:p"),
            {"p": hdr[meta["party_col"]]},
        )
    ).mappings().one_or_none()
    address = (
        await session.execute(
            text("SELECT line1, line2, city, state, pincode FROM party_address "
                 "WHERE party_id=:p ORDER BY is_default DESC, id LIMIT 1"),
            {"p": hdr[meta["party_col"]]},
        )
    ).mappings().first()

    lines = (
        await session.execute(
            text(
                f"SELECT l.line_no, p.code AS product_code, p.name AS product, l.hsn_code, "
                f"l.entered_qty, u.code AS unit, l.rate, l.gross_amount, l.discount_amount, "
                f"l.header_discount_alloc, l.taxable, l.gst_rate, l.cgst, l.sgst, l.igst, "
                f"l.line_total, l.remarks "
                f"FROM {meta['line_table']} l "
                f"JOIN product p ON p.id = l.product_id "
                f"LEFT JOIN unit_of_measure u ON u.id = l.entered_unit_id "
                f"WHERE l.{meta['line_fk']}=:i ORDER BY l.line_no"
            ),
            {"i": doc_id},
        )
    ).mappings().all()

    # GST summary by rate — the table a tax invoice is expected to carry
    tax_rows = (
        await session.execute(
            text(
                f"SELECT l.gst_rate, SUM(l.taxable) AS taxable, SUM(l.cgst) AS cgst, "
                f"SUM(l.sgst) AS sgst, SUM(l.igst) AS igst "
                f"FROM {meta['line_table']} l WHERE l.{meta['line_fk']}=:i "
                f"GROUP BY l.gst_rate ORDER BY l.gst_rate"
            ),
            {"i": doc_id},
        )
    ).mappings().all()

    payments: list[dict] = []
    if doc_type in ("sales_bill", "purchase_bill"):
        from app.services import allocation as alloc

        history = await alloc.document_payments(session, principal.org_id, doc_type, doc_id)
        payments = history["payments"]

    payment_type = None
    if hdr.get("payment_type_id"):
        payment_type = (
            await session.execute(
                text("SELECT name FROM payment_type WHERE id=:i"), {"i": hdr["payment_type_id"]}
            )
        ).scalar_one_or_none()

    return {
        "doc_type": doc_type,
        "title": meta["title"],
        "party_label": meta["party_label"],
        "settings": await print_settings(session, principal.org_id),
        "org": {"name": org["name"]},
        "branch": {k: _s(v) for k, v in dict(branch or {}).items()},
        "party": {
            **{k: _s(v) for k, v in dict(party or {}).items()},
            "address": {k: _s(v) for k, v in dict(address or {}).items()} if address else None,
        },
        "document": {
            "id": hdr["id"], "doc_no": hdr["doc_no"], "status": hdr["status"],
            "date": hdr[meta["date_col"]], "doc_datetime": hdr.get("doc_datetime"),
            "supply_type": hdr.get("supply_type"), "price_mode": hdr.get("price_mode"),
            "revision_no": hdr.get("revision_no"), "amended_from": hdr.get("amended_from"),
            "remarks": hdr.get("remarks"), "payment_type": payment_type,
            "supplier_invoice_no": hdr.get("supplier_invoice_no"),
        },
        "lines": [{k: _s(v) for k, v in dict(r).items()} for r in lines],
        "tax_summary": [{k: _s(v) for k, v in dict(r).items()} for r in tax_rows],
        "totals": {
            k: _s(hdr.get(k))
            for k in ("gross_total", "line_discount_total", "discount_amount", "taxable_total",
                      "tax_total", "card_charges", "round_off", "grand_total",
                      "paid_amount", "balance_amount")
        },
        "amount_in_words": amount_in_words(Decimal(hdr["grand_total"])),
        "payments": payments,
    }
