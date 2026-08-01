"""Invoice money model (v2 §3/§4) — one pure implementation for all four
document types (purchase bill/return, sales bill/return).

No database, no session: it takes line inputs plus header parameters and
returns the computed lines and totals. That keeps the arithmetic testable on
its own and guarantees purchase and sales agree to the paisa.

Order of operations, which is what makes GST come out right:

    gross      = qty x rate                          (rate is per ENTERED unit)
    - line discount (explicit amount, else pct)
    = net
    - overall discount, allocated pro-rata across lines by net
    = net after discounts
    -> if price_mode is 'inclusive' the net already contains GST, so the
       taxable is extracted (net / (1 + rate/100)); otherwise the net IS the
       taxable and GST is added on top
    + card charges                                   (post-tax, no GST)
    + round off                                      (auto to the rupee)
    = grand total
    - paid  = balance

The overall discount is deliberately applied BEFORE tax and spread across the
lines rather than knocked off the grand total: a post-tax lump sum would leave
each line's GST overstated and the GST reports wrong.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

Q2 = Decimal("0.01")
ZERO = Decimal("0")


def q2(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Q2, rounding=ROUND_HALF_UP)


@dataclass
class LineIn:
    """One invoice line as the user entered it."""

    qty: Decimal                              # entered qty, in entered_unit
    rate: Decimal                             # price per ENTERED unit
    gst_rate: Decimal = ZERO
    discount_pct: Decimal = ZERO
    discount_amount: Decimal | None = None    # explicit wins over pct


@dataclass
class LineOut:
    gross: Decimal = ZERO
    discount: Decimal = ZERO
    header_discount_alloc: Decimal = ZERO
    taxable: Decimal = ZERO
    gst_rate: Decimal = ZERO
    cgst: Decimal = ZERO
    sgst: Decimal = ZERO
    igst: Decimal = ZERO
    tax: Decimal = ZERO
    line_total: Decimal = ZERO


@dataclass
class Totals:
    gross_total: Decimal = ZERO
    line_discount_total: Decimal = ZERO
    header_discount: Decimal = ZERO
    taxable_total: Decimal = ZERO
    tax_total: Decimal = ZERO
    cgst_total: Decimal = ZERO
    sgst_total: Decimal = ZERO
    igst_total: Decimal = ZERO
    card_charges: Decimal = ZERO
    round_off: Decimal = ZERO
    grand_total: Decimal = ZERO
    paid_amount: Decimal = ZERO
    balance_amount: Decimal = ZERO


@dataclass
class Computed:
    lines: list[LineOut] = field(default_factory=list)
    totals: Totals = field(default_factory=Totals)


class MoneyError(ValueError):
    """The figures don't make sense (discount bigger than the line, etc.)."""


def _split_gst(tax: Decimal, supply_type: str):
    """Inter-state is IGST; intra-state splits CGST/SGST so the halves still
    sum to the tax exactly (the odd paisa goes to SGST)."""
    if supply_type == "inter":
        return ZERO, ZERO, tax
    cgst = q2(tax / 2)
    return cgst, q2(tax - cgst), ZERO


def _allocate(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split `total` across `weights` pro-rata, to the paisa, with the largest
    remainders absorbing the rounding so the parts sum to `total` exactly."""
    if total == 0 or not weights:
        return [ZERO for _ in weights]
    weight_sum = sum(weights)
    if weight_sum <= 0:
        return [ZERO for _ in weights]

    exact = [(total * w / weight_sum) for w in weights]
    floored = [e.quantize(Q2, rounding=ROUND_DOWN) for e in exact]
    shortfall = total - sum(floored)

    # hand out the leftover paisa, biggest fractional part first
    order = sorted(range(len(weights)), key=lambda i: exact[i] - floored[i], reverse=True)
    for idx in order:
        if shortfall < Q2:
            break
        floored[idx] += Q2
        shortfall -= Q2
    return floored


def compute(
    lines: list[LineIn],
    *,
    supply_type: str = "intra",
    price_mode: str = "exclusive",
    header_discount_pct: Decimal = ZERO,
    header_discount_amount: Decimal | None = None,
    card_charges: Decimal = ZERO,
    round_off: Decimal | None = None,
    paid_amount: Decimal = ZERO,
) -> Computed:
    if not lines:
        raise MoneyError("an invoice needs at least one line")
    if price_mode not in ("exclusive", "inclusive"):
        raise MoneyError(f"unknown price_mode {price_mode!r}")

    # --- 1. line gross and line discount -------------------------------
    outs = [LineOut(gst_rate=Decimal(ln.gst_rate or 0)) for ln in lines]
    nets: list[Decimal] = []
    for ln, out in zip(lines, outs):
        out.gross = q2(Decimal(ln.qty) * Decimal(ln.rate))
        if ln.discount_amount is not None:
            out.discount = q2(ln.discount_amount)
        else:
            out.discount = q2(out.gross * Decimal(ln.discount_pct or 0) / 100)
        if out.discount > out.gross:
            raise MoneyError(f"line discount {out.discount} exceeds line amount {out.gross}")
        nets.append(out.gross - out.discount)

    net_sum = sum(nets)

    # --- 2. overall discount, allocated pro-rata across the lines ------
    if header_discount_amount is not None:
        header_discount = q2(header_discount_amount)
    else:
        header_discount = q2(net_sum * Decimal(header_discount_pct or 0) / 100)
    if header_discount > net_sum:
        raise MoneyError(f"overall discount {header_discount} exceeds invoice value {net_sum}")

    allocs = _allocate(header_discount, nets)

    # --- 3. per line: taxable, GST, line total -------------------------
    for out, net, alloc in zip(outs, nets, allocs):
        out.header_discount_alloc = alloc
        net_after = net - alloc
        rate = out.gst_rate
        if price_mode == "inclusive":
            # the entered price already contains the tax — back it out
            out.taxable = q2(net_after / (1 + rate / 100)) if rate else q2(net_after)
            out.tax = q2(net_after - out.taxable)
        else:
            out.taxable = q2(net_after)
            out.tax = q2(out.taxable * rate / 100)
        out.cgst, out.sgst, out.igst = _split_gst(out.tax, supply_type)
        out.line_total = q2(out.taxable + out.tax)

    # --- 4. totals, card charges, round off ----------------------------
    t = Totals(
        gross_total=q2(sum((o.gross for o in outs), ZERO)),
        line_discount_total=q2(sum((o.discount for o in outs), ZERO)),
        header_discount=header_discount,
        taxable_total=q2(sum((o.taxable for o in outs), ZERO)),
        tax_total=q2(sum((o.tax for o in outs), ZERO)),
        cgst_total=q2(sum((o.cgst for o in outs), ZERO)),
        sgst_total=q2(sum((o.sgst for o in outs), ZERO)),
        igst_total=q2(sum((o.igst for o in outs), ZERO)),
        card_charges=q2(card_charges or 0),
    )
    pre_round = q2(sum((o.line_total for o in outs), ZERO) + t.card_charges)
    if round_off is None:
        # nearest rupee
        t.round_off = q2(pre_round.quantize(Decimal("1"), rounding=ROUND_HALF_UP) - pre_round)
    else:
        t.round_off = q2(round_off)
    t.grand_total = q2(pre_round + t.round_off)

    t.paid_amount = q2(paid_amount or 0)
    if t.paid_amount < 0:
        raise MoneyError("paid amount cannot be negative")
    if t.paid_amount > t.grand_total:
        raise MoneyError(f"paid amount {t.paid_amount} exceeds invoice total {t.grand_total}")
    t.balance_amount = q2(t.grand_total - t.paid_amount)

    return Computed(lines=outs, totals=t)
