"""Idempotent demo seed: 1 tenant, 1 branch, full coffee menu, punchcard 10+1, barista, owner.

Re-run safely — existing rows are updated (prices/sizes/flags), new ones inserted.

Usage:
    python -m scripts.seed
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import delete, select

from app.core.db import session_scope
from app.core.security import hash_secret
from app.models import (
    Branch,
    Campaign,
    CampaignBranch,
    Product,
    Staff,
    StaffBranch,
    Tenant,
    TransactionItem,
)


DEMO_TENANT_SLUG = "demo"
DEMO_BARISTA_PIN = "1234"
DEMO_OWNER_EMAIL = "mirafzal"
DEMO_OWNER_PASSWORD = "mirafzal"
DEMO_CURRENCY = "UZS"

# (sku, name, category, size, base_price, loyalty_eligible)
# Sizes: S=детский, M=стандарт, L=средний, XL=большой, ESP=эспрессо-размер
PRODUCT_SEEDS: list[tuple[str, str, str, str | None, str, bool]] = [
    # ---- Espresso ----
    ("ESP",              "Эспрессо",                    "coffee", None, "22000", True),

    # ---- Американо ----
    ("AMER-S",           "Американо",                   "coffee", "S",  "22000", True),
    ("AMER-M",           "Американо",                   "coffee", "M",  "26000", True),
    ("AMER-L",           "Американо",                   "coffee", "L",  "30000", True),
    ("AMER-XL",          "Американо",                   "coffee", "XL", "34000", True),

    # ---- Капучино ----
    ("CAPP-S",           "Капучино",                    "coffee", "S",  "25000", True),
    ("CAPP-M",           "Капучино",                    "coffee", "M",  "30000", True),
    ("CAPP-L",           "Капучино",                    "coffee", "L",  "34000", True),
    ("CAPP-XL",          "Капучино",                    "coffee", "XL", "38000", True),

    # ---- Латте ----
    ("LATT-S",           "Латте",                       "coffee", "S",  "25000", True),
    ("LATT-M",           "Латте",                       "coffee", "M",  "30000", True),
    ("LATT-L",           "Латте",                       "coffee", "L",  "34000", True),
    ("LATT-XL",          "Латте",                       "coffee", "XL", "38000", True),

    # ---- Флэт Уайт ----
    ("FLW-S",            "Флэт Уайт",                   "coffee", "S",  "30000", True),

    # ---- Caffelito ----
    ("CAFL-M",           "Caffelito кофе",              "coffee", "M",  "38000", True),
    ("CAFL-L",           "Caffelito кофе",              "coffee", "L",  "42000", True),
    ("CAFL-XL",          "Caffelito кофе",              "coffee", "XL", "46000", True),

    # ---- Раф ----
    ("RAF-L",            "Раф",                         "coffee", "L",  "45000", True),

    # ---- Какао ----
    ("COCO-S",           "Какао",                       "coffee", "S",  "24000", True),
    ("COCO-M",           "Какао",                       "coffee", "M",  "30000", True),
    ("COCO-L",           "Какао",                       "coffee", "L",  "36000", True),
    ("COCO-XL",          "Какао",                       "coffee", "XL", "42000", True),

    # ---- Матча Латте ----
    ("MATCHA-L",         "Матча Латте",                 "coffee", "L",  "32000", True),

    # ---- Горячий шоколад ----
    ("HC-ESP",           "Горячий шоколад",             "coffee", "ESP","30000", True),
    ("HC-S",             "Горячий шоколад",             "coffee", "S",  "40000", True),

    # ---- Не Чай ----
    ("NOTEA-L",          "Не Чай",                      "tea",    "L",  "34000", False),

    # ---- Айс Американо ----
    ("ICE-AMER-L",       "Айс Американо",               "coffee", "L",  "26000", True),
    ("ICE-AMER-XL",      "Айс Американо",               "coffee", "XL", "30000", True),

    # ---- Айс Капучино ----
    ("ICE-CAPP-L",       "Айс Капучино",                "coffee", "L",  "26000", True),
    ("ICE-CAPP-XL",      "Айс Капучино",                "coffee", "XL", "34000", True),

    # ---- Айс Латте ----
    ("ICE-LATT-L",       "Айс Латте",                   "coffee", "L",  "26000", True),
    ("ICE-LATT-XL",      "Айс Латте",                   "coffee", "XL", "34000", True),

    # ---- Бамбл ----
    ("BUMBLE-XL",        "Бамбл",                       "coffee", "XL", "38000", True),

    # ---- Фрапетто ----
    ("FRAP-L",           "Фрапетто",                    "coffee", "L",  "40000", True),
    ("FRAP-XL",          "Фрапетто",                    "coffee", "XL", "48000", True),

    # ---- Милкшейк (не кофе — без бонусов) ----
    ("MILKSHK-L",        "Милкшейк",                    "drink",  "L",  "36000", False),
    ("MILKSHK-XL",       "Милкшейк",                    "drink",  "XL", "48000", False),

    # ---- Мохито ----
    ("MOJ-XL",           "Мохито",                      "drink",  "XL", "38000", False),

    # ---- Айс Матча Латте ----
    ("ICE-MATCHA-XL",    "Айс Матча Латте",             "coffee", "XL", "32000", True),

    # ---- Эспрессо Тоник ----
    ("ESP-TONIC-XL",     "Эспрессо Тоник",              "coffee", "XL", "48000", True),

    # ---- Лимонады ----
    ("LEM-BERRY-XL",     "Лимонад Ягодный",             "drink",  "XL", "42000", False),
    ("LEM-SBT-XL",       "Лимонад Облепиховый",         "drink",  "XL", "42000", False),
    ("LEM-GINGER-XL",    "Лимонад Имбирный",            "drink",  "XL", "42000", False),

    # ---- Сэндвичи ----
    ("SAND-MEAT",        "Сэндвич Мясной микс",         "food",   None, "32000", False),
    ("SAND-TURKEY",      "Сэндвич Индейка",             "food",   None, "32000", False),
    ("SAND-SAUS",        "Сэндвич Колбасный микс",      "food",   None, "32000", False),
    ("SAND-TUNA",        "Сэндвич Тунец",               "food",   None, "38000", False),

    # ---- Чиабатта ----
    ("CIAB-GURMAN",      "Чиабатта Гурман",             "food",   None, "32000", False),
    ("CIAB-PIKANTE",     "Чиабатта Пиканте",            "food",   None, "32000", False),

    # ---- Круассаны ----
    ("CRO-CLASSIC",      "Круассан Классический",       "food",   None, "30000", False),
    ("CRO-PISTACHIO",    "Круассан С фисташкой",        "food",   None, "45000", False),
    ("CRO-HAZELNUT",     "Круассан Фундук",             "food",   None, "45000", False),
    ("CRO-PIST",         "Круассан Фисташка",           "food",   None, "45000", False),
    ("CRO-BERRY",        "Круассан Ягоды",              "food",   None, "45000", False),

    # ---- Десерты ----
    ("SANSEB",           "Сан Себастьян (чизкейк)",     "food",   None, "45000", False),
    ("COOK-CLASSIC",     "Cookies Классический",        "food",   None, "20000", False),
    ("COOK-BROWNIE",     "Cookies Брауни",              "food",   None, "20000", False),
    ("STROOP",           "Stroop Wafel",                "food",   None, "10000", False),
    ("WAFER-125",        "Wafers 125g (фундук)",        "food",   None, "40000", False),
    ("WAFER-30",         "Wafer 30g (фундук)",          "food",   None, "13000", False),
    ("CHOCBALL",         "Chocolate Balls",             "food",   None, "30000", False),
    ("DUBAI",            "Дубайский шоколад",           "food",   None, "50000", False),

    # ---- Мороженое ----
    ("ICE-PLOMBIR",      "Мороженое Пломбир",           "food",   None, "22000", False),
    ("ICE-STRAW",        "Мороженое Клубника",          "food",   None, "22000", False),
    ("ICE-CHOC",         "Мороженое Шоколад",           "food",   None, "22000", False),
    ("ICE-SALTCARAMEL",  "Мороженое Солёная карамель",  "food",   None, "22000", False),
    ("MINIPOPS",         "Mini Pops",                   "food",   None, "58000", False),

    # ---- Дрип кофе ----
    ("DRIP-COL",         "Дрип кофе Колумбия",          "coffee", "S",  "15000", True),
    ("DRIP-COL-PACK",    "Дрип кофе Колумбия (пакет)",  "coffee", "XL", "65000", False),
    ("DRIP-ETH",         "Дрип кофе Эфиопия",           "coffee", "S",  "15000", True),
    ("DRIP-ETH-PACK",    "Дрип кофе Эфиопия (пакет)",   "coffee", "XL", "70000", False),
    ("DRIP-CREMA",       "Дрип кофе Крема эспрессо",    "coffee", "S",  "15000", True),
    ("DRIP-CREMA-PACK",  "Дрип кофе Крема эспрессо (пакет)","coffee","XL","65000", False),
    ("DRIP-BREW",        "Дрип кофе (заварить)",        "coffee", "M",  "22000", True),
    ("DRIP-COLD",        "Дрип кофе (холодный)",        "coffee", "L",  "26000", True),

    # ---- Кофе в зернах 250г ----
    ("BEAN-CREMA",       "Кофе в зернах Крема эспрессо 250г","merch", None, "110000", False),
    ("BEAN-BRAZIL",      "Кофе в зернах Бразилия 250г", "merch",  None, "110000", False),
    ("BEAN-COL",         "Кофе в зернах Колумбия 250г", "merch",  None, "130000", False),
    ("BEAN-ETHIOPIA",    "Кофе в зернах Эфиопия 250г",  "merch",  None, "140000", False),
]


async def seed() -> None:
    async with session_scope() as session:
        # ---- tenant ----
        tenant = (
            await session.execute(
                select(Tenant).where(Tenant.slug == DEMO_TENANT_SLUG)
            )
        ).scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(
                name="Demo Coffee",
                slug=DEMO_TENANT_SLUG,
                plan="growth",
                status="active",
                default_currency=DEMO_CURRENCY,
                default_timezone="Asia/Tashkent",
            )
            session.add(tenant)
            await session.flush()
            print(f"Created tenant: {tenant.id}  currency={DEMO_CURRENCY}")
        elif tenant.default_currency != DEMO_CURRENCY:
            print(
                f"Tenant currency: {tenant.default_currency} -> {DEMO_CURRENCY}"
            )
            tenant.default_currency = DEMO_CURRENCY

        # ---- branch ----
        branch = (
            await session.execute(
                select(Branch).where(
                    Branch.tenant_id == tenant.id, Branch.name == "Central"
                )
            )
        ).scalar_one_or_none()
        if branch is None:
            branch = Branch(
                tenant_id=tenant.id,
                name="Central",
                address="Tashkent, Amir Temur 1",
                timezone="Asia/Tashkent",
                status="active",
            )
            session.add(branch)
            await session.flush()
            print(f"Created branch: {branch.id}")

        # ---- products: wipe everything not in the new menu, then upsert ----
        existing_products = (
            await session.execute(
                select(Product).where(Product.tenant_id == tenant.id)
            )
        ).scalars().all()
        existing_by_sku: dict[str, Product] = {
            p.sku: p for p in existing_products if p.sku
        }
        new_skus = {sku for sku, *_ in PRODUCT_SEEDS}

        # Which existing products are still referenced from transaction_items?
        # Those we cannot delete (FK without CASCADE) — deactivate instead.
        referenced_ids = set(
            (
                await session.execute(
                    select(TransactionItem.product_id)
                    .where(TransactionItem.product_id.is_not(None))
                    .distinct()
                )
            ).scalars()
        )

        to_drop_ids: list = []
        deactivated = 0
        for prod in existing_products:
            if prod.sku in new_skus:
                continue
            if prod.id in referenced_ids:
                if prod.is_active:
                    prod.is_active = False
                    deactivated += 1
            else:
                to_drop_ids.append(prod.id)
        deleted = 0
        if to_drop_ids:
            res = await session.execute(
                delete(Product).where(Product.id.in_(to_drop_ids))
            )
            deleted = res.rowcount or len(to_drop_ids)
        await session.flush()

        inserted = 0
        updated = 0
        for sku, name, cat, size, price, loyalty in PRODUCT_SEEDS:
            price_d = Decimal(price)
            existing = existing_by_sku.get(sku)
            if existing is None:
                session.add(
                    Product(
                        tenant_id=tenant.id,
                        sku=sku,
                        name=name,
                        category=cat,
                        size=size,
                        base_price=price_d,
                        is_loyalty_eligible=loyalty,
                        is_active=True,
                    )
                )
                inserted += 1
            else:
                changed = False
                if existing.name != name:
                    existing.name = name; changed = True
                if existing.category != cat:
                    existing.category = cat; changed = True
                if existing.size != size:
                    existing.size = size; changed = True
                if Decimal(existing.base_price) != price_d:
                    existing.base_price = price_d; changed = True
                if existing.is_loyalty_eligible != loyalty:
                    existing.is_loyalty_eligible = loyalty; changed = True
                if not existing.is_active:
                    existing.is_active = True; changed = True
                if changed:
                    updated += 1
        await session.flush()
        print(
            f"Products: +{inserted} new, ~{updated} updated, "
            f"-{deleted} deleted, -{deactivated} deactivated (FK-referenced), "
            f"total in menu={len(PRODUCT_SEEDS)}"
        )

        # ---- punchcard 10+1 campaign ----
        camp = (
            await session.execute(
                select(Campaign).where(
                    Campaign.tenant_id == tenant.id, Campaign.code == "COFFEE_10_PLUS_1"
                )
            )
        ).scalar_one_or_none()
        if camp is None:
            camp = Campaign(
                tenant_id=tenant.id,
                code="COFFEE_10_PLUS_1",
                name="10 + 1 free coffee",
                type="punchcard",
                status="active",
                rules={
                    "type": "punchcard",
                    "trigger": {
                        "product_category": "coffee",
                        "loyalty_eligible_only": True,
                    },
                    "stamps_required": 10,
                    "reward": {"kind": "free_product", "category": "coffee"},
                    "expires_after_days": 90,
                    "cooldown_minutes": 0,
                },
            )
            session.add(camp)
            await session.flush()
            session.add(CampaignBranch(campaign_id=camp.id, branch_id=branch.id))
            print(f"Created campaign: {camp.id}")

        # ---- barista ----
        barista = (
            await session.execute(
                select(Staff).where(
                    Staff.tenant_id == tenant.id, Staff.full_name == "Demo Barista"
                )
            )
        ).scalar_one_or_none()
        if barista is None:
            barista = Staff(
                tenant_id=tenant.id,
                full_name="Demo Barista",
                role="barista",
                status="active",
                pin_hash=hash_secret(DEMO_BARISTA_PIN),
            )
            session.add(barista)
            await session.flush()
            session.add(StaffBranch(staff_id=barista.id, branch_id=branch.id))
            print(f"Created barista: {barista.id}; PIN={DEMO_BARISTA_PIN}")

        # ---- owner (web admin) ----
        owner = (
            await session.execute(
                select(Staff).where(
                    Staff.tenant_id == tenant.id, Staff.email == DEMO_OWNER_EMAIL
                )
            )
        ).scalar_one_or_none()
        if owner is None:
            owner = Staff(
                tenant_id=tenant.id,
                full_name="Demo Owner",
                email=DEMO_OWNER_EMAIL,
                role="owner",
                status="active",
                password_hash=hash_secret(DEMO_OWNER_PASSWORD),
            )
            session.add(owner)
            await session.flush()
            session.add(StaffBranch(staff_id=owner.id, branch_id=branch.id))
            print(
                f"Created owner: {owner.id};\n"
                f"  Admin login: {DEMO_OWNER_EMAIL} / {DEMO_OWNER_PASSWORD}"
            )

    print("Seed OK.")
    print(f"Set BOT_TENANT_ID={tenant.id} in .env if you have multiple tenants.")
    print(
        "\nLog into admin: http://127.0.0.1:8000/admin/login\n"
        f"  email:    {DEMO_OWNER_EMAIL}\n"
        f"  password: {DEMO_OWNER_PASSWORD}"
    )


if __name__ == "__main__":
    asyncio.run(seed())
