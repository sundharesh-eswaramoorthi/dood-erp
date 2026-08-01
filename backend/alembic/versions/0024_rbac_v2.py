"""v2 §7 User & Roles.

The v1 catalogue had 11 permissions, too coarse for the v2 matrix: a Sales
Executive must have Sales but not Purchase, not Stock Adjustment and not
Accounts, while `stock.write` bundled adjust + transfer + verify into one.
And nothing expressed "edit current date invoice" as a right distinct from
"edit previous date invoice", which V2.8's amendment endpoints now enforce.

The five v1 roles are RENAMED in place rather than replaced, so every existing
user keeps their role assignment (user_role points at role.id, which does not
change). Purchase Executive is genuinely new.

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-01
"""
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("party.read", "View parties"),
    ("party.create", "Create parties"),
    ("party.edit", "Edit parties"),
    ("product.read", "View products & units"),
    ("product.create", "Create products"),
    ("product.edit", "Edit products"),
    ("stock.read", "View stock"),
    ("stock.write", "Adjust/transfer stock (legacy umbrella)"),
    ("stock.adjust", "Stock adjustments (damage, shortage, opening)"),
    ("stock.transfer", "Stock transfers between branches/godowns"),
    ("stock.verify", "Physical stock verification"),
    ("purchase.read", "View purchases"),
    ("purchase.create", "Create purchase bills & returns"),
    ("purchase.order", "Create purchase orders"),
    ("sales.read", "View sales"),
    ("sales.create", "Create sale orders/bills"),
    ("sales.return", "Create sales returns"),
    ("delivery.read", "View deliveries"),
    ("delivery.update", "Update delivery status"),
    ("invoice.edit.today", "Edit an invoice dated today"),
    ("invoice.edit.backdated", "Edit an invoice dated before today"),
    ("invoice.cancel", "Cancel a posted invoice"),
    ("accounts.read", "View accounts & payments"),
    ("accounts.manage", "Manage bank accounts & payments"),
    ("reports.view", "View reports"),
    ("users.manage", "Manage users & roles"),
    ("settings.manage", "Manage settings"),
]

# v1 code -> (v2 code, v2 display name)
RENAMES = [
    ("super_user", "super_admin", "Super Admin"),
    ("manager", "branch_manager", "Branch Manager"),
    ("stock_manager", "store_keeper", "Store Keeper"),
    ("salesman", "sales_executive", "Sales Executive"),
    ("delivery_boy", "delivery_staff", "Delivery Staff"),
]

# v2 §7 matrix. Super Admin is not listed: it carries the "*" wildcard via
# app_user.is_superuser.
ROLE_PERMS = {
    "branch_manager": [
        "party.read", "party.create", "party.edit",
        "product.read", "product.create", "product.edit",
        "stock.read", "stock.write", "stock.adjust", "stock.transfer", "stock.verify",
        "purchase.read", "purchase.create", "purchase.order",
        "sales.read", "sales.create", "sales.return",
        "delivery.read", "delivery.update",
        "invoice.edit.today", "invoice.edit.backdated", "invoice.cancel",
        "accounts.read", "accounts.manage", "reports.view",
        # explicitly NOT users.manage / settings.manage (v2 §7)
    ],
    "sales_executive": [
        "party.read", "party.create", "party.edit",
        "product.read", "stock.read",
        "sales.read", "sales.create", "sales.return",
        "delivery.read", "reports.view",
        "invoice.edit.today",
        # NOT purchase, NOT stock.adjust, NOT accounts,
        # NOT invoice.edit.backdated (v2 §7)
    ],
    "purchase_executive": [
        "party.read", "party.create", "party.edit",
        "product.read", "stock.read",
        "purchase.read", "purchase.create", "purchase.order",
        "reports.view", "invoice.edit.today",
        # NOT sales, NOT invoice.edit.backdated (v2 §7)
    ],
    "store_keeper": [
        "product.read", "product.edit",
        "stock.read", "stock.write", "stock.adjust", "stock.transfer", "stock.verify",
        "purchase.read", "sales.read",
    ],
    "delivery_staff": [
        "sales.read", "delivery.read", "delivery.update", "party.read", "product.read",
    ],
}


def upgrade() -> None:
    conn = op.get_bind()

    for code, desc in PERMISSIONS:
        conn.exec_driver_sql(
            "INSERT INTO permission (code, description) VALUES (%s, %s) "
            "ON CONFLICT (code) DO UPDATE SET description = EXCLUDED.description",
            (code, desc),
        )

    # rename in place so user_role assignments survive
    for old, new, name in RENAMES:
        conn.exec_driver_sql(
            "UPDATE role SET code = %s, name = %s WHERE code = %s", (new, name, old)
        )

    # the one genuinely new role
    conn.exec_driver_sql(
        "INSERT INTO role (org_id, code, name) "
        "SELECT id, 'purchase_executive', 'Purchase Executive' FROM organization "
        "ON CONFLICT (org_id, code) DO NOTHING"
    )

    # rebuild the mappings for every non-superuser role
    for role_code, perms in ROLE_PERMS.items():
        conn.exec_driver_sql(
            "DELETE FROM role_permission WHERE role_id IN "
            "(SELECT id FROM role WHERE code = %s)",
            (role_code,),
        )
        for perm in perms:
            conn.exec_driver_sql(
                "INSERT INTO role_permission (role_id, permission_code) "
                "SELECT id, %s FROM role WHERE code = %s ON CONFLICT DO NOTHING",
                (perm, role_code),
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("DELETE FROM role_permission WHERE role_id IN "
                         "(SELECT id FROM role WHERE code = 'purchase_executive')")
    conn.exec_driver_sql("DELETE FROM role WHERE code = 'purchase_executive'")
    for old, new, _ in RENAMES:
        conn.exec_driver_sql("UPDATE role SET code = %s WHERE code = %s", (old, new))
