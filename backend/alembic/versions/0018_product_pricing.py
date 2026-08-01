"""v2 §2 Product: pricing master and the sub-unit.

The product had no price at all, so every invoice line required a hand-typed
rate. It now carries a sale and a purchase price, plus whether those prices
already include GST (v2's "Sale price(tax)"), which seeds the invoice's
price_mode.

The sub-unit is stored on the product for the form's benefit AND mirrored into
unit_conversion, so the existing to_base() engine converts it with no special
casing: sub_unit_qty is how many sub-units make one base unit (1 BAG = 50 KG),
and the conversion row is its reciprocal (1 KG = 0.02 BAG).

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-01
"""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE product ADD COLUMN sale_price      NUMERIC(18,4) CHECK (sale_price >= 0);
ALTER TABLE product ADD COLUMN purchase_price  NUMERIC(18,4) CHECK (purchase_price >= 0);
ALTER TABLE product ADD COLUMN price_inclusive BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE product ADD COLUMN sub_unit_id     BIGINT REFERENCES unit_of_measure(id);
ALTER TABLE product ADD COLUMN sub_unit_qty    NUMERIC(20,8) CHECK (sub_unit_qty > 0);

-- v2 §2 lists opening stock as part of the product form; the movement itself
-- still goes through a stock_adjustment('opening'), these just remember what
-- was entered so the form can show it back.
ALTER TABLE product ADD COLUMN opening_qty     NUMERIC(20,6);
ALTER TABLE product ADD COLUMN opening_rate    NUMERIC(18,4);
ALTER TABLE product ADD COLUMN opening_as_of   DATE;
ALTER TABLE product ADD COLUMN opening_godown_id BIGINT;

CREATE INDEX ix_product_active ON product (org_id, is_active);
"""

DOWN = """
DROP INDEX IF EXISTS ix_product_active;
ALTER TABLE product DROP COLUMN IF EXISTS opening_godown_id;
ALTER TABLE product DROP COLUMN IF EXISTS opening_as_of;
ALTER TABLE product DROP COLUMN IF EXISTS opening_rate;
ALTER TABLE product DROP COLUMN IF EXISTS opening_qty;
ALTER TABLE product DROP COLUMN IF EXISTS sub_unit_qty;
ALTER TABLE product DROP COLUMN IF EXISTS sub_unit_id;
ALTER TABLE product DROP COLUMN IF EXISTS price_inclusive;
ALTER TABLE product DROP COLUMN IF EXISTS purchase_price;
ALTER TABLE product DROP COLUMN IF EXISTS sale_price;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
