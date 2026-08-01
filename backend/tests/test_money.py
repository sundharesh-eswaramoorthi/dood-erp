"""Unit tests for the v2 invoice money model (app.services.money).

Pure arithmetic — no database — so the rounding and allocation rules that every
invoice depends on are pinned down here rather than inferred from a posted doc.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services import money

D = Decimal


def line(qty, rate, gst=0, dpct=0, damt=None):
    return money.LineIn(qty=D(qty), rate=D(rate), gst_rate=D(gst),
                        discount_pct=D(dpct), discount_amount=damt)


def test_simple_exclusive_intra():
    c = money.compute([line(10, 100, gst=5)])
    m, t = c.lines[0], c.totals
    assert m.gross == D("1000.00")
    assert m.taxable == D("1000.00")
    assert m.cgst == D("25.00") and m.sgst == D("25.00") and m.igst == D("0")
    assert m.line_total == D("1050.00")
    assert t.grand_total == D("1050.00")
    assert t.round_off == D("0.00")
    assert t.balance_amount == D("1050.00")


def test_inter_state_is_igst():
    c = money.compute([line(10, 100, gst=5)], supply_type="inter")
    m = c.lines[0]
    assert m.igst == D("50.00") and m.cgst == 0 and m.sgst == 0


def test_tax_inclusive_backs_the_tax_out():
    """105 entered at 5% GST is 100 taxable + 5 tax, not 105 + 5.25."""
    c = money.compute([line(1, "105", gst=5)], price_mode="inclusive")
    m = c.lines[0]
    assert m.taxable == D("100.00")
    assert m.tax == D("5.00")
    assert m.line_total == D("105.00")


def test_line_discount_pct_and_amount():
    by_pct = money.compute([line(10, 100, gst=5, dpct=10)]).lines[0]
    assert by_pct.discount == D("100.00")
    assert by_pct.taxable == D("900.00")
    assert by_pct.tax == D("45.00")

    # an explicit amount overrides the percentage
    by_amt = money.compute([line(10, 100, gst=5, dpct=10, damt=D("250"))]).lines[0]
    assert by_amt.discount == D("250.00")
    assert by_amt.taxable == D("750.00")


def test_header_discount_is_allocated_pro_rata_and_sums_exactly():
    c = money.compute(
        [line(1, 100, gst=5), line(1, 200, gst=5), line(1, 700, gst=5)],
        header_discount_amount=D("100"),
    )
    allocs = [m.header_discount_alloc for m in c.lines]
    assert sum(allocs) == D("100.00"), "allocation must not lose or invent paisa"
    assert allocs == [D("10.00"), D("20.00"), D("70.00")]
    assert c.totals.taxable_total == D("900.00")


def test_header_discount_allocation_handles_thirds():
    """10 across three equal lines can't divide evenly — the remainder paisa
    must still be handed out so the parts sum to the whole."""
    c = money.compute([line(1, 100), line(1, 100), line(1, 100)],
                      header_discount_amount=D("10"))
    allocs = [m.header_discount_alloc for m in c.lines]
    assert sum(allocs) == D("10.00")
    assert max(allocs) - min(allocs) <= D("0.01")


def test_header_discount_applies_before_tax():
    """A post-tax lump discount would leave GST overstated — this checks the
    tax follows the discounted taxable."""
    c = money.compute([line(1, 1000, gst=18)], header_discount_amount=D("100"))
    m = c.lines[0]
    assert m.taxable == D("900.00")
    assert m.tax == D("162.00")          # 18% of 900, not of 1000
    assert c.totals.grand_total == D("1062.00")


def test_card_charges_and_auto_round_off():
    c = money.compute([line(1, "1000.40", gst=0)], card_charges=D("9.20"))
    t = c.totals
    assert t.card_charges == D("9.20")
    # 1000.40 + 9.20 = 1009.60 -> rounds to 1010.00
    assert t.round_off == D("0.40")
    assert t.grand_total == D("1010.00")


def test_explicit_round_off_wins():
    c = money.compute([line(1, "1000.40")], round_off=D("-0.40"))
    assert c.totals.grand_total == D("1000.00")


def test_paid_and_balance():
    c = money.compute([line(10, 100, gst=5)], paid_amount=D("50"))
    assert c.totals.paid_amount == D("50.00")
    assert c.totals.balance_amount == D("1000.00")


def test_cgst_plus_sgst_always_equals_tax():
    """Odd-paisa taxes must not drift when halved."""
    for rate in ("0.01", "3.33", "99.99", "1234.57"):
        c = money.compute([line(1, rate, gst=5)])
        m = c.lines[0]
        assert m.cgst + m.sgst == m.tax


def test_totals_are_the_sum_of_the_lines():
    c = money.compute([line(2, "33.33", gst=12), line(7, "11.11", gst=5)], header_discount_pct=D("7.5"))
    t = c.totals
    assert t.taxable_total == sum(m.taxable for m in c.lines)
    assert t.tax_total == sum(m.tax for m in c.lines)
    assert t.cgst_total + t.sgst_total + t.igst_total == t.tax_total


def test_rejects_impossible_figures():
    with pytest.raises(money.MoneyError):
        money.compute([line(1, 100, damt=D("200"))])          # discount > line
    with pytest.raises(money.MoneyError):
        money.compute([line(1, 100)], header_discount_amount=D("500"))  # > invoice
    with pytest.raises(money.MoneyError):
        money.compute([line(1, 100)], paid_amount=D("500"))   # paid > total
    with pytest.raises(money.MoneyError):
        money.compute([])                                     # no lines
