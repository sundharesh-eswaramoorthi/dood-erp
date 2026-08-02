"""Idempotent dev seed: one org, one branch + godown, the permission catalog,
the five system roles, a super-user, and the party numbering series.

Run:  python -m app.seed
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.core.security import hash_password
from app.services.numbering import current_fin_year

# v2 §7 catalogue — kept in step with alembic 0024 (which is what an existing
# install runs); this is the fresh-install path.
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

ROLES = [
    ("super_admin", "Super Admin"),
    ("branch_manager", "Branch Manager"),
    ("sales_executive", "Sales Executive"),
    ("purchase_executive", "Purchase Executive"),
    ("store_keeper", "Store Keeper"),
    ("delivery_staff", "Delivery Staff"),
]

# role -> permission codes (super_admin uses the "*" wildcard via is_superuser)
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
    ],
    "sales_executive": [
        "party.read", "party.create", "party.edit",
        "product.read", "stock.read",
        "sales.read", "sales.create", "sales.return",
        "delivery.read", "reports.view", "invoice.edit.today",
    ],
    "purchase_executive": [
        "party.read", "party.create", "party.edit",
        "product.read", "stock.read",
        "purchase.read", "purchase.create", "purchase.order",
        "reports.view", "invoice.edit.today",
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


async def _scalar(conn, sql: str, **params):
    return (await conn.execute(text(sql), params)).scalar()


async def seed() -> None:
    async with SessionLocal() as s:
        async with s.begin():
            org_id = await _scalar(s, "SELECT id FROM organization LIMIT 1")
            if org_id is None:
                org_id = await _scalar(
                    s, "INSERT INTO organization (name) VALUES (:n) RETURNING id",
                    n="Cholavin Traders",
                )

            # Scope the seed session so RLS-protected masters can be inserted.
            await s.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(org_id)})

            branch_id = await _scalar(
                s, "SELECT id FROM branch WHERE org_id=:o ORDER BY id LIMIT 1", o=org_id
            )
            if branch_id is None:
                branch_id = await _scalar(
                    s, "INSERT INTO branch (org_id, name) VALUES (:o, :n) RETURNING id",
                    o=org_id, n="Main Branch",
                )

            for gname in ("Main Godown", "Secondary Godown"):
                exists_g = await _scalar(
                    s, "SELECT id FROM godown WHERE branch_id=:b AND name=:n", b=branch_id, n=gname
                )
                if exists_g is None:
                    await s.execute(
                        text("INSERT INTO godown (org_id, branch_id, name) VALUES (:o, :b, :n)"),
                        {"o": org_id, "b": branch_id, "n": gname},
                    )

            for code, desc in PERMISSIONS:
                await s.execute(
                    text(
                        "INSERT INTO permission (code, description) VALUES (:c, :d) "
                        "ON CONFLICT (code) DO NOTHING"
                    ),
                    {"c": code, "d": desc},
                )

            for code, name in ROLES:
                await s.execute(
                    text(
                        "INSERT INTO role (org_id, code, name) VALUES (:o, :c, :n) "
                        "ON CONFLICT (org_id, code) DO NOTHING"
                    ),
                    {"o": org_id, "c": code, "n": name},
                )

            # role -> permission mappings
            for role_code, perms in ROLE_PERMS.items():
                rid = await _scalar(s, "SELECT id FROM role WHERE org_id=:o AND code=:c", o=org_id, c=role_code)
                for perm in perms:
                    await s.execute(
                        text("INSERT INTO role_permission (role_id, permission_code) VALUES (:r, :p) "
                             "ON CONFLICT DO NOTHING"),
                        {"r": rid, "p": perm},
                    )

            # super-user
            user_id = await _scalar(
                s, "SELECT id FROM app_user WHERE username=:u", u=settings.SEED_ADMIN_USERNAME
            )
            if user_id is None:
                user_id = await _scalar(
                    s,
                    "INSERT INTO app_user (org_id, username, password_hash, full_name, is_superuser) "
                    "VALUES (:o, :u, :p, :n, true) RETURNING id",
                    o=org_id,
                    u=settings.SEED_ADMIN_USERNAME,
                    p=hash_password(settings.SEED_ADMIN_PASSWORD),
                    n="Administrator",
                )

            await s.execute(
                text(
                    "INSERT INTO user_branch_access (user_id, branch_id) VALUES (:u, :b) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"u": user_id, "b": branch_id},
            )

            # party numbering series (org-wide) for the current financial year
            fy = current_fin_year()
            exists = await _scalar(
                s,
                "SELECT id FROM numbering_series WHERE org_id=:o AND branch_id IS NULL "
                "AND doc_type='party' AND fin_year=:fy",
                o=org_id, fy=fy,
            )
            if exists is None:
                await s.execute(
                    text(
                        "INSERT INTO numbering_series (org_id, branch_id, doc_type, fin_year, prefix, pad_width) "
                        "VALUES (:o, NULL, 'party', :fy, 'CUST-', 4)"
                    ),
                    {"o": org_id, "fy": fy},
                )
            # org-wide numbering series for stock documents.
            # 'product' belongs here as much as 'party' does: since V2.12 a blank
            # product code is allocated from it, and migration 0025 only back-fills
            # series for orgs that already existed — on a clean install there are
            # none yet, so without this every product needs a hand-typed code.
            for doc_type, prefix in [("product", "PRD-"),
                                     ("stock_adjustment", "ADJ-"), ("stock_transfer", "TRF-"),
                                     ("stock_verification", "VER-"), ("journal", "JV-"),
                                     ("purchase_bill", "PB-"), ("purchase_return", "PR-"),
                                     ("purchase_order", "PO-"), ("sale_order", "SO-"),
                                     ("delivery", "DLV-"), ("sales_bill", "SB-"),
                                     ("sales_return", "SR-"), ("payment_voucher", "PV-"),
                                     ("expense", "EXP-")]:
                await s.execute(
                    text(
                        "INSERT INTO numbering_series (org_id, branch_id, doc_type, fin_year, prefix, pad_width) "
                        "VALUES (:o, NULL, :dt, :fy, :px, 4) "
                        "ON CONFLICT (org_id, COALESCE(branch_id, 0), doc_type, fin_year) DO NOTHING"
                    ),
                    {"o": org_id, "dt": doc_type, "fy": fy, "px": prefix},
                )

            # base units of measure + a default product category
            for code, name in [("BAG", "Bag"), ("KG", "Kilogram"), ("PCS", "Pieces"), ("BOX", "Box")]:
                await s.execute(
                    text(
                        "INSERT INTO unit_of_measure (org_id, code, name) VALUES (:o, :c, :n) "
                        "ON CONFLICT (org_id, code) DO NOTHING"
                    ),
                    {"o": org_id, "c": code, "n": name},
                )
            await s.execute(
                text(
                    "INSERT INTO product_category (org_id, name) VALUES (:o, 'General') "
                    "ON CONFLICT (org_id, name) DO NOTHING"
                ),
                {"o": org_id},
            )

            # GST tax-rate master
            for name, rate in [("GST 0%", 0), ("GST 5%", 5), ("GST 12%", 12), ("GST 18%", 18), ("GST 28%", 28)]:
                await s.execute(
                    text(
                        "INSERT INTO tax_rate (org_id, name, rate) VALUES (:o, :n, :r) "
                        "ON CONFLICT (org_id, name) DO NOTHING"
                    ),
                    {"o": org_id, "n": name, "r": rate},
                )

            # a few starter tags
            for name, color in [("Wholesale", "#1E3A5F"), ("Retail", "#2E7D5B"), ("Priority", "#B96D28")]:
                await s.execute(
                    text(
                        "INSERT INTO tag_definition (org_id, name, color) VALUES (:o, :n, :c) "
                        "ON CONFLICT (org_id, name) DO NOTHING"
                    ),
                    {"o": org_id, "n": name, "c": color},
                )

            # default cash/bank accounts
            for aname, atype in [("Cash", "cash"), ("HDFC Bank", "bank"), ("Petty Cash", "petty_cash")]:
                await s.execute(
                    text(
                        "INSERT INTO cash_bank_account (org_id, name, account_type) VALUES (:o, :n, :t) "
                        "ON CONFLICT (org_id, name) DO NOTHING"
                    ),
                    {"o": org_id, "n": aname, "t": atype},
                )
            # Payment types (v2 §3). Migration 0022 seeds these by CROSS JOIN on
            # organization, which finds nothing on a fresh database — migrations
            # run before this file creates the org. Without them the split-payment
            # editor has no modes to offer and Payment Mode-wise Sales has nothing
            # to group by, so the seed has to cover the clean-install path too.
            for pname, pkind, pord in (
                ("Cash", "cash", 1), ("UPI", "upi", 2), ("Card", "card", 3),
                ("Cheque", "cheque", 4), ("Bank Transfer", "bank", 5), ("Credit", "credit", 6),
            ):
                await s.execute(
                    text("INSERT INTO payment_type (org_id, name, kind, sort_order) "
                         "VALUES (:o, :n, :k, :s) ON CONFLICT DO NOTHING"),
                    {"o": org_id, "n": pname, "k": pkind, "s": pord},
                )

            # expense categories
            for cname in ("Rent", "Salary", "Transport", "Utilities", "Misc"):
                await s.execute(
                    text("INSERT INTO expense_category (org_id, name) VALUES (:o, :n) "
                         "ON CONFLICT (org_id, name) DO NOTHING"),
                    {"o": org_id, "n": cname},
                )

            # feature flags (Purchase Order toggle etc.)
            for key, val in [("feature.purchase_order", '{"enabled": true}'), ("feature.sale_order", '{"enabled": true}')]:
                await s.execute(
                    text(
                        "INSERT INTO system_setting (org_id, key, value) VALUES (:o, :k, CAST(:v AS jsonb)) "
                        "ON CONFLICT (org_id, key) DO NOTHING"
                    ),
                    {"o": org_id, "k": key, "v": val},
                )

        print(
            f"[seed] org={org_id} branch={branch_id} user='{settings.SEED_ADMIN_USERNAME}' "
            f"password='{settings.SEED_ADMIN_PASSWORD}' ready."
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
