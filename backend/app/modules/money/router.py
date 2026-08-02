"""Money preview — run the invoice arithmetic without persisting anything.

The invoice screens need to show the customer a running total before the
document is posted. Rather than reimplement the v2 money rules in TypeScript
(and let the two drift), the UI calls this and renders exactly what the posting
path would compute.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.deps import Principal, get_principal
from app.modules.shared import SUPPLY_TYPE, MoneyHeaderIn
from app.services import money

router = APIRouter()


class PreviewLineIn(BaseModel):
    qty: Decimal = Field(default=Decimal(0))
    rate: Decimal = Field(default=Decimal(0))
    gst_rate: Decimal = Field(default=Decimal(0))
    discount_pct: Decimal = Field(default=Decimal(0))
    discount_amount: Decimal | None = None


class PreviewIn(MoneyHeaderIn):
    lines: list[PreviewLineIn] = Field(default_factory=list)


@router.post("/money/preview")
async def preview(payload: PreviewIn, principal: Principal = Depends(get_principal)):
    usable = [ln for ln in payload.lines if ln.qty > 0]
    if not usable:
        return {"lines": [], "totals": None}
    try:
        computed = money.compute(
            [
                money.LineIn(qty=ln.qty, rate=ln.rate, gst_rate=ln.gst_rate,
                             discount_pct=ln.discount_pct, discount_amount=ln.discount_amount)
                for ln in usable
            ],
            supply_type=SUPPLY_TYPE, price_mode=payload.price_mode,
            header_discount_pct=payload.discount_pct,
            header_discount_amount=payload.discount_amount,
            card_charges=payload.card_charges, round_off=payload.round_off,
            paid_amount=payload.paid_amount,
        )
    except money.MoneyError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    t = computed.totals
    # Decimals go out as strings, like every other money field in the API — a
    # float here would show "1710" where the posted document shows "1710.00".
    return {
        "lines": [
            {"gross": str(m.gross), "discount": str(m.discount),
             "header_discount_alloc": str(m.header_discount_alloc), "taxable": str(m.taxable),
             "gst_rate": str(m.gst_rate), "cgst": str(m.cgst), "sgst": str(m.sgst),
             "igst": str(m.igst), "tax": str(m.tax), "line_total": str(m.line_total)}
            for m in computed.lines
        ],
        "totals": {
            "gross_total": str(t.gross_total), "line_discount_total": str(t.line_discount_total),
            "discount_amount": str(t.header_discount), "taxable_total": str(t.taxable_total),
            "tax_total": str(t.tax_total), "cgst_total": str(t.cgst_total),
            "sgst_total": str(t.sgst_total), "igst_total": str(t.igst_total),
            "card_charges": str(t.card_charges), "round_off": str(t.round_off),
            "grand_total": str(t.grand_total), "paid_amount": str(t.paid_amount),
            "balance_amount": str(t.balance_amount),
        },
    }
