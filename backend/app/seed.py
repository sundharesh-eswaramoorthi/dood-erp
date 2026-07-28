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

PERMISSIONS = [
    ("party.read", "View parties"),
    ("party.create", "Create/edit parties"),
    ("product.read", "View products & units"),
    ("product.create", "Create/edit products"),
    ("stock.read", "View stock"),
    ("stock.write", "Adjust/transfer stock"),
    ("sales.create", "Create sale orders/bills"),
    ("purchase.create", "Create purchase bills"),
    ("reports.view", "View reports"),
    ("settings.manage", "Manage settings & users"),
]

ROLES = [
    ("super_user", "Super User"),
    ("manager", "Manager"),
    ("stock_manager", "Stock Manager"),
    ("salesman", "Salesman"),
    ("delivery_boy", "Delivery Boy"),
]


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

            godown_id = await _scalar(
                s, "SELECT id FROM godown WHERE branch_id=:b LIMIT 1", b=branch_id
            )
            if godown_id is None:
                await s.execute(
                    text("INSERT INTO godown (org_id, branch_id, name) VALUES (:o, :b, :n)"),
                    {"o": org_id, "b": branch_id, "n": "Main Godown"},
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
            # org-wide numbering series for stock documents
            for doc_type, prefix in [("stock_adjustment", "ADJ-"), ("stock_transfer", "TRF-"),
                                     ("stock_verification", "VER-")]:
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
