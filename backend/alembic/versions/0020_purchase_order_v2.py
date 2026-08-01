"""v2 §3: "Purchase order — same as purchase bills (advance instead of paid)".

The PO was a stub: supplier, dates, and lines with a bare rate. It now carries
the same money block as every other document (0017), except that money handed
over up front is an ADVANCE rather than a payment — the goods have not arrived,
so the supplier owes us until they do.

Lines gain the godown they are destined for, GST, discounts and computed
amounts, plus received_qty so the PO can report how much of it has been billed.

Status grows a 'partial' step between open and closed, and 'closed' now means
fully received.

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-01
"""
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

UP = """
-- the 0017 money block, with advance in place of paid
ALTER TABLE purchase_order ADD COLUMN supply_type    TEXT NOT NULL DEFAULT 'intra'
                                                      CHECK (supply_type IN ('intra','inter'));
ALTER TABLE purchase_order ADD COLUMN price_mode     TEXT NOT NULL DEFAULT 'exclusive'
                                                      CHECK (price_mode IN ('exclusive','inclusive'));
ALTER TABLE purchase_order ADD COLUMN godown_id      BIGINT;
ALTER TABLE purchase_order ADD COLUMN gross_total    NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE purchase_order ADD COLUMN line_discount_total NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE purchase_order ADD COLUMN discount_pct   NUMERIC(5,2)  NOT NULL DEFAULT 0;
ALTER TABLE purchase_order ADD COLUMN discount_amount NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE purchase_order ADD COLUMN taxable_total  NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE purchase_order ADD COLUMN tax_total      NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE purchase_order ADD COLUMN card_charges   NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE purchase_order ADD COLUMN round_off      NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE purchase_order ADD COLUMN grand_total    NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE purchase_order ADD COLUMN advance_amount NUMERIC(14,2) NOT NULL DEFAULT 0
                                                      CHECK (advance_amount >= 0);
ALTER TABLE purchase_order ADD COLUMN balance_amount NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE purchase_order ADD COLUMN payment_account_id BIGINT;
ALTER TABLE purchase_order ADD COLUMN remarks        TEXT;
ALTER TABLE purchase_order ADD COLUMN doc_datetime   TIMESTAMPTZ;
UPDATE purchase_order SET doc_datetime = order_date::timestamptz;
ALTER TABLE purchase_order ALTER COLUMN doc_datetime SET NOT NULL;
ALTER TABLE purchase_order ALTER COLUMN doc_datetime SET DEFAULT now();

-- 'partial' sits between open and closed; closed == fully received
ALTER TABLE purchase_order DROP CONSTRAINT purchase_order_status_check;
ALTER TABLE purchase_order ADD CONSTRAINT purchase_order_status_check
    CHECK (status IN ('open','approved','partial','closed','cancelled'));

ALTER TABLE purchase_order_line ADD COLUMN godown_id             BIGINT;
ALTER TABLE purchase_order_line ADD COLUMN base_qty              NUMERIC(20,6) NOT NULL DEFAULT 0;
ALTER TABLE purchase_order_line ADD COLUMN received_qty          NUMERIC(20,6) NOT NULL DEFAULT 0;
ALTER TABLE purchase_order_line ADD COLUMN hsn_code              TEXT;
ALTER TABLE purchase_order_line ADD COLUMN remarks               TEXT;
ALTER TABLE purchase_order_line ADD COLUMN gross_amount          NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE purchase_order_line ADD COLUMN discount_pct          NUMERIC(5,2)  NOT NULL DEFAULT 0;
ALTER TABLE purchase_order_line ADD COLUMN discount_amount       NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE purchase_order_line ADD COLUMN header_discount_alloc NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE purchase_order_line ADD COLUMN taxable               NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE purchase_order_line ADD COLUMN gst_rate              NUMERIC(5,2)  NOT NULL DEFAULT 0;
ALTER TABLE purchase_order_line ADD COLUMN cgst                  NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE purchase_order_line ADD COLUMN sgst                  NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE purchase_order_line ADD COLUMN igst                  NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE purchase_order_line ADD COLUMN line_total            NUMERIC(14,2) NOT NULL DEFAULT 0;

-- Which PO line a bill line satisfies. Recorded, never inferred: a PO can
-- legitimately carry the same product on several lines (different godowns,
-- rates or lots), so matching receipts back by product_id alone credits the
-- wrong line and the order never closes.
ALTER TABLE purchase_bill_line ADD COLUMN po_line_no INT;

CREATE INDEX ix_pb_po ON purchase_bill (org_id, po_id) WHERE po_id IS NOT NULL;
"""

DOWN = """
DROP INDEX IF EXISTS ix_pb_po;
ALTER TABLE purchase_bill_line DROP COLUMN IF EXISTS po_line_no;
ALTER TABLE purchase_order_line
    DROP COLUMN IF EXISTS godown_id, DROP COLUMN IF EXISTS base_qty,
    DROP COLUMN IF EXISTS received_qty, DROP COLUMN IF EXISTS hsn_code,
    DROP COLUMN IF EXISTS remarks, DROP COLUMN IF EXISTS gross_amount,
    DROP COLUMN IF EXISTS discount_pct, DROP COLUMN IF EXISTS discount_amount,
    DROP COLUMN IF EXISTS header_discount_alloc, DROP COLUMN IF EXISTS taxable,
    DROP COLUMN IF EXISTS gst_rate, DROP COLUMN IF EXISTS cgst,
    DROP COLUMN IF EXISTS sgst, DROP COLUMN IF EXISTS igst,
    DROP COLUMN IF EXISTS line_total;
ALTER TABLE purchase_order DROP CONSTRAINT IF EXISTS purchase_order_status_check;
ALTER TABLE purchase_order ADD CONSTRAINT purchase_order_status_check
    CHECK (status IN ('open','approved','closed','cancelled'));
ALTER TABLE purchase_order
    DROP COLUMN IF EXISTS supply_type, DROP COLUMN IF EXISTS price_mode,
    DROP COLUMN IF EXISTS godown_id, DROP COLUMN IF EXISTS gross_total,
    DROP COLUMN IF EXISTS line_discount_total, DROP COLUMN IF EXISTS discount_pct,
    DROP COLUMN IF EXISTS discount_amount, DROP COLUMN IF EXISTS taxable_total,
    DROP COLUMN IF EXISTS tax_total, DROP COLUMN IF EXISTS card_charges,
    DROP COLUMN IF EXISTS round_off, DROP COLUMN IF EXISTS grand_total,
    DROP COLUMN IF EXISTS advance_amount, DROP COLUMN IF EXISTS balance_amount,
    DROP COLUMN IF EXISTS payment_account_id, DROP COLUMN IF EXISTS remarks,
    DROP COLUMN IF EXISTS doc_datetime;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
