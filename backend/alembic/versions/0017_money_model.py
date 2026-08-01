"""v2 §3/§4 invoice money model, applied uniformly to all four document types.

Header gains: price mode (tax-inclusive entry), overall discount, card charges,
round off, paid/balance, the settling account, remarks and a real date+time.
Lines gain: their own godown (the "multi godown invoice"), an HSN snapshot,
remarks, a line discount, the gross before discounts, and their share of the
overall discount.

The godown move is the structural part: purchase kept one godown on the header,
and sales bills had none at all. Existing rows are backfilled from wherever the
godown used to live so nothing is orphaned, then the column goes NOT NULL.

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-01
"""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

HEADERS = ("purchase_bill", "purchase_return", "sales_bill", "sales_return")
LINES = ("purchase_bill_line", "purchase_return_line", "sales_bill_line", "sales_return_line")

# effective-date column per header, used to seed doc_datetime
DATE_COL = {
    "purchase_bill": "bill_date",
    "purchase_return": "return_date",
    "sales_bill": "bill_date",
    "sales_return": "return_date",
}


def _header_sql(t: str) -> str:
    return f"""
ALTER TABLE {t} ADD COLUMN price_mode      TEXT NOT NULL DEFAULT 'exclusive'
                                            CHECK (price_mode IN ('exclusive','inclusive'));
ALTER TABLE {t} ADD COLUMN gross_total     NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE {t} ADD COLUMN line_discount_total NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE {t} ADD COLUMN discount_pct    NUMERIC(5,2)  NOT NULL DEFAULT 0;
ALTER TABLE {t} ADD COLUMN discount_amount NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE {t} ADD COLUMN card_charges    NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE {t} ADD COLUMN round_off       NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE {t} ADD COLUMN paid_amount     NUMERIC(14,2) NOT NULL DEFAULT 0
                                            CHECK (paid_amount >= 0);
ALTER TABLE {t} ADD COLUMN balance_amount  NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE {t} ADD COLUMN payment_account_id BIGINT;
ALTER TABLE {t} ADD COLUMN remarks         TEXT;
ALTER TABLE {t} ADD COLUMN doc_datetime    TIMESTAMPTZ;
UPDATE {t} SET doc_datetime = {DATE_COL[t]}::timestamptz,
               gross_total  = taxable_total,
               balance_amount = grand_total;
ALTER TABLE {t} ALTER COLUMN doc_datetime SET NOT NULL;
ALTER TABLE {t} ALTER COLUMN doc_datetime SET DEFAULT now();
"""


def _line_sql(t: str) -> str:
    return f"""
ALTER TABLE {t} ADD COLUMN godown_id             BIGINT;
ALTER TABLE {t} ADD COLUMN hsn_code              TEXT;
ALTER TABLE {t} ADD COLUMN remarks               TEXT;
ALTER TABLE {t} ADD COLUMN gross_amount          NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE {t} ADD COLUMN discount_pct          NUMERIC(5,2)  NOT NULL DEFAULT 0;
ALTER TABLE {t} ADD COLUMN discount_amount       NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE {t} ADD COLUMN header_discount_alloc NUMERIC(14,2) NOT NULL DEFAULT 0;
UPDATE {t} SET gross_amount = taxable;
"""


BACKFILL = """
-- purchase kept a single godown on the header; push it down to the lines
UPDATE purchase_bill_line l SET godown_id = h.godown_id
  FROM purchase_bill h WHERE h.id = l.bill_id;
UPDATE purchase_return_line l SET godown_id = h.godown_id
  FROM purchase_return h WHERE h.id = l.return_id;
UPDATE sales_return_line l SET godown_id = h.godown_id
  FROM sales_return h WHERE h.id = l.return_id;

-- sales bills never stored a godown: recover it from the order line the bill
-- was raised against, then fall back to any godown in the bill's branch.
-- (the target table can't be referenced inside a FROM ... JOIN ON, so the
--  line_no match lives in the WHERE)
UPDATE sales_bill_line l SET godown_id = sol.godown_id
  FROM sales_bill h, sale_order_line sol
 WHERE h.id = l.bill_id
   AND sol.order_id = h.sale_order_id
   AND sol.line_no = l.line_no;
UPDATE sales_bill_line l SET godown_id = g.id
  FROM sales_bill h
  JOIN LATERAL (SELECT id FROM godown WHERE branch_id = h.branch_id ORDER BY id LIMIT 1) g ON TRUE
 WHERE h.id = l.bill_id AND l.godown_id IS NULL;

-- v2 §3 wants qty + unit on every invoice line; sales bills only had base qty
ALTER TABLE sales_bill_line ADD COLUMN entered_qty     NUMERIC(20,6);
ALTER TABLE sales_bill_line ADD COLUMN entered_unit_id BIGINT;
UPDATE sales_bill_line l SET entered_qty = l.base_qty, entered_unit_id = p.base_unit_id
  FROM product p WHERE p.id = l.product_id;

-- purchase bills may now cite the PO they came from (v2 §3 "PO number")
ALTER TABLE purchase_bill ADD COLUMN po_id BIGINT REFERENCES purchase_order(id);
"""

TIGHTEN = """
ALTER TABLE purchase_bill_line   ALTER COLUMN godown_id SET NOT NULL;
ALTER TABLE purchase_return_line ALTER COLUMN godown_id SET NOT NULL;
ALTER TABLE sales_return_line    ALTER COLUMN godown_id SET NOT NULL;
ALTER TABLE sales_bill_line      ALTER COLUMN godown_id SET NOT NULL;
CREATE INDEX ix_pbl_godown ON purchase_bill_line (org_id, godown_id);
CREATE INDEX ix_sbl_godown ON sales_bill_line (org_id, godown_id);

-- the header godown becomes a default for the UI, not the source of truth
ALTER TABLE purchase_bill   ALTER COLUMN godown_id DROP NOT NULL;
ALTER TABLE purchase_return ALTER COLUMN godown_id DROP NOT NULL;
ALTER TABLE sales_return    ALTER COLUMN godown_id DROP NOT NULL;
"""

DOWN_HEADER_COLS = [
    "price_mode", "gross_total", "line_discount_total", "discount_pct", "discount_amount",
    "card_charges", "round_off", "paid_amount", "balance_amount", "payment_account_id",
    "remarks", "doc_datetime",
]
DOWN_LINE_COLS = [
    "godown_id", "hsn_code", "remarks", "gross_amount", "discount_pct",
    "discount_amount", "header_discount_alloc",
]


def upgrade() -> None:
    for t in HEADERS:
        op.execute(_header_sql(t))
    for t in LINES:
        op.execute(_line_sql(t))
    op.execute(BACKFILL)
    op.execute(TIGHTEN)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_pbl_godown; DROP INDEX IF EXISTS ix_sbl_godown;")
    op.execute("ALTER TABLE purchase_bill DROP COLUMN IF EXISTS po_id;")
    op.execute(
        "ALTER TABLE sales_bill_line DROP COLUMN IF EXISTS entered_qty;"
        "ALTER TABLE sales_bill_line DROP COLUMN IF EXISTS entered_unit_id;"
    )
    for t in LINES:
        for c in DOWN_LINE_COLS:
            op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS {c};")
    for t in HEADERS:
        for c in DOWN_HEADER_COLS:
            op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS {c};")
