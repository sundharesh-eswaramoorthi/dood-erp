"""v2 §4 Sales: the sale order gets the same money block as everything else, and
sales bills stop requiring an order.

A counter sale had no route through the system: sales_bill.sale_order_id was
nullable but bill_order() was the only writer, so a walk-in customer needed a
fake order raised and billed. The column stays nullable and V2.6 adds the
direct path; this migration only widens 'partial' delivery status and prices
the order.

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-01
"""
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

UP = """
-- the 0017 money block on the order, so a quote/order prices exactly like the
-- bill it becomes
ALTER TABLE sale_order ADD COLUMN supply_type    TEXT NOT NULL DEFAULT 'intra'
                                                  CHECK (supply_type IN ('intra','inter'));
ALTER TABLE sale_order ADD COLUMN price_mode     TEXT NOT NULL DEFAULT 'exclusive'
                                                  CHECK (price_mode IN ('exclusive','inclusive'));
ALTER TABLE sale_order ADD COLUMN gross_total    NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE sale_order ADD COLUMN line_discount_total NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE sale_order ADD COLUMN discount_pct   NUMERIC(5,2)  NOT NULL DEFAULT 0;
ALTER TABLE sale_order ADD COLUMN discount_amount NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE sale_order ADD COLUMN taxable_total  NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE sale_order ADD COLUMN tax_total      NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE sale_order ADD COLUMN card_charges   NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE sale_order ADD COLUMN round_off      NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE sale_order ADD COLUMN grand_total    NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE sale_order ADD COLUMN remarks        TEXT;
ALTER TABLE sale_order ADD COLUMN doc_datetime   TIMESTAMPTZ;
UPDATE sale_order SET doc_datetime = order_date::timestamptz;
ALTER TABLE sale_order ALTER COLUMN doc_datetime SET NOT NULL;
ALTER TABLE sale_order ALTER COLUMN doc_datetime SET DEFAULT now();

-- v2 §4 lists the order status as pending / delivered / cancelled; 'partial'
-- is what a part-delivered order actually is, and the UI needs to say so.
ALTER TABLE sale_order DROP CONSTRAINT sale_order_status_check;
ALTER TABLE sale_order ADD CONSTRAINT sale_order_status_check
    CHECK (status IN ('pending','partial','delivered','cancelled'));

ALTER TABLE sale_order_line ADD COLUMN hsn_code              TEXT;
ALTER TABLE sale_order_line ADD COLUMN remarks               TEXT;
ALTER TABLE sale_order_line ADD COLUMN gross_amount          NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE sale_order_line ADD COLUMN discount_pct          NUMERIC(5,2)  NOT NULL DEFAULT 0;
ALTER TABLE sale_order_line ADD COLUMN discount_amount       NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE sale_order_line ADD COLUMN header_discount_alloc NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE sale_order_line ADD COLUMN taxable               NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE sale_order_line ADD COLUMN gst_rate              NUMERIC(5,2)  NOT NULL DEFAULT 0;
ALTER TABLE sale_order_line ADD COLUMN cgst                  NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE sale_order_line ADD COLUMN sgst                  NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE sale_order_line ADD COLUMN igst                  NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE sale_order_line ADD COLUMN line_total            NUMERIC(14,2) NOT NULL DEFAULT 0;

-- Seed the GST rate on existing order lines from the product, so that a stored
-- 0 means "genuinely zero-rated" and billing can trust the order line instead
-- of re-deriving the rate (which would re-price an old order whenever the
-- product master changed).
UPDATE sale_order_line l SET gst_rate = COALESCE(p.gst_rate, 0)
  FROM product p WHERE p.id = l.product_id;

-- counter sales: no order, so no order number to look them up by
CREATE INDEX ix_sb_counter ON sales_bill (org_id, branch_id, bill_date)
    WHERE sale_order_id IS NULL;
"""

DOWN = """
DROP INDEX IF EXISTS ix_sb_counter;
ALTER TABLE sale_order_line
    DROP COLUMN IF EXISTS hsn_code, DROP COLUMN IF EXISTS remarks,
    DROP COLUMN IF EXISTS gross_amount, DROP COLUMN IF EXISTS discount_pct,
    DROP COLUMN IF EXISTS discount_amount, DROP COLUMN IF EXISTS header_discount_alloc,
    DROP COLUMN IF EXISTS taxable, DROP COLUMN IF EXISTS gst_rate,
    DROP COLUMN IF EXISTS cgst, DROP COLUMN IF EXISTS sgst,
    DROP COLUMN IF EXISTS igst, DROP COLUMN IF EXISTS line_total;
UPDATE sale_order SET status='pending' WHERE status='partial';
ALTER TABLE sale_order DROP CONSTRAINT IF EXISTS sale_order_status_check;
ALTER TABLE sale_order ADD CONSTRAINT sale_order_status_check
    CHECK (status IN ('pending','delivered','cancelled'));
ALTER TABLE sale_order
    DROP COLUMN IF EXISTS supply_type, DROP COLUMN IF EXISTS price_mode,
    DROP COLUMN IF EXISTS gross_total, DROP COLUMN IF EXISTS line_discount_total,
    DROP COLUMN IF EXISTS discount_pct, DROP COLUMN IF EXISTS discount_amount,
    DROP COLUMN IF EXISTS taxable_total, DROP COLUMN IF EXISTS tax_total,
    DROP COLUMN IF EXISTS card_charges, DROP COLUMN IF EXISTS round_off,
    DROP COLUMN IF EXISTS grand_total, DROP COLUMN IF EXISTS remarks,
    DROP COLUMN IF EXISTS doc_datetime;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
