#!/usr/bin/env python3
"""
Khana Bazaar — Database Seed Script
====================================
Populates PostgreSQL with categories, products, stores, inventory,
and test user accounts (no Firebase required).

Usage (from backend/app/):
    uv run python scripts/seed_database.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.base import User, UserRole
from app.models.catalog import Category, MasterProduct
from app.models.store import Store, StoreInventory

TEST_USERS = [
    {"email": "admin@khanabazaar.dev", "display_name": "Platform Admin", "role": UserRole.Admin},
    {"email": "seller@khanabazaar.dev", "display_name": "Ravi Sharma", "role": UserRole.Seller},
    {"email": "seller2@khanabazaar.dev", "display_name": "Krishna Patel", "role": UserRole.Seller},
    {"email": "seller3@khanabazaar.dev", "display_name": "Balaji Ramaswamy", "role": UserRole.Seller},
    {"email": "customer@khanabazaar.dev", "display_name": "Priya Verma", "role": UserRole.Customer},
]

CATEGORIES = [
    {"name": "Fruits & Vegetables", "description": "Fresh produce from local farms"},
    {"name": "Dairy & Bakery", "description": "Milk, paneer, bread, and baked goods"},
    {"name": "Staples & Grains", "description": "Rice, atta, dal, and cooking essentials"},
    {"name": "Snacks & Beverages", "description": "Chips, biscuits, tea, coffee, and cold drinks"},
]

PRODUCTS = [
    {"name": "Fresh Tomatoes", "description": "Firm, red tomatoes — perfect for curries and chutneys", "category_idx": 0, "image_url": "/images/products/tomatoes.jpg", "base_price": 40},
    {"name": "Green Coriander Bunch", "description": "Fresh dhania for garnishing and chutney", "category_idx": 0, "image_url": "/images/products/coriander.jpg", "base_price": 15},
    {"name": "Onions (Pyaaz)", "description": "Medium-sized onions, a kitchen staple", "category_idx": 0, "image_url": "/images/products/onions.jpg", "base_price": 35},
    {"name": "Amul Taza Milk (1L)", "description": "Toned milk, pasteurized & homogenized", "category_idx": 1, "image_url": "/images/products/milk.jpg", "base_price": 54},
    {"name": "Amul Paneer (200g)", "description": "Fresh cottage cheese block for sabzi & tikka", "category_idx": 1, "image_url": "/images/products/paneer.jpg", "base_price": 90},
    {"name": "Britannia Bread (400g)", "description": "Soft white sandwich bread", "category_idx": 1, "image_url": "/images/products/bread.jpg", "base_price": 45},
    {"name": "Toor Dal (1kg)", "description": "Premium quality arhar dal for everyday cooking", "category_idx": 2, "image_url": "/images/products/toor-dal.jpg", "base_price": 160},
    {"name": "Basmati Rice (5kg)", "description": "Long grain aged basmati — perfect for biryani", "category_idx": 2, "image_url": "/images/products/rice.jpg", "base_price": 450},
    {"name": "Aashirvaad Atta (5kg)", "description": "Whole wheat flour for soft rotis", "category_idx": 2, "image_url": "/images/products/atta.jpg", "base_price": 280},
    {"name": "Lay's Classic Salted (52g)", "description": "Crispy potato chips, classic flavor", "category_idx": 3, "image_url": "/images/products/lays.jpg", "base_price": 20},
    {"name": "Tata Tea Gold (500g)", "description": "Premium blend of Assam & Darjeeling tea", "category_idx": 3, "image_url": "/images/products/tea.jpg", "base_price": 270},
    {"name": "Parle-G Biscuits (800g)", "description": "India's iconic glucose biscuits — since 1939", "category_idx": 3, "image_url": "/images/products/parle-g.jpg", "base_price": 80},
]

STORES = [
    {
        "name": "Sharma General Store",
        "seller_idx": 1,
        "address_line1": "12, MG Road",
        "address_line2": "Sector 14",
        "landmark": "Near HUDA City Centre",
        "city": "Gurugram",
        "state": "Haryana",
        "pincode": "122001",
        "country": "India",
        "latitude": 28.4595,
        "longitude": 77.0266,
    },
    {
        "name": "Krishna Supermart",
        "seller_idx": 2,
        "address_line1": "45, Nehru Nagar",
        "address_line2": "Andheri West",
        "landmark": "Opposite Lokhandwala Complex",
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400058",
        "country": "India",
        "latitude": 19.1364,
        "longitude": 72.8296,
    },
    {
        "name": "Balaji Fresh Market",
        "seller_idx": 3,
        "address_line1": "78, Rajaji Street",
        "address_line2": "T. Nagar",
        "landmark": "Next to Pothys",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "pincode": "600017",
        "country": "India",
        "latitude": 13.0418,
        "longitude": 80.2341,
    },
]


_ADDRESS_KEYS = (
    "address_line1",
    "address_line2",
    "landmark",
    "city",
    "state",
    "pincode",
    "country",
    "latitude",
    "longitude",
)

# Inventory: (store_idx, product_idx, price, stock)
INVENTORIES = [
    # Sharma General Store
    (0, 0, 42, 50), (0, 1, 18, 30), (0, 2, 38, 60),
    (0, 3, 56, 20), (0, 4, 95, 15),
    (0, 6, 165, 25), (0, 7, 460, 10), (0, 8, 285, 12),
    (0, 9, 20, 100), (0, 10, 275, 18), (0, 11, 82, 40),
    # Krishna Supermart
    (1, 0, 45, 40), (1, 3, 54, 35), (1, 4, 92, 20),
    (1, 5, 48, 25), (1, 6, 158, 30),
    (1, 9, 20, 60), (1, 10, 268, 15), (1, 11, 78, 50),
    # Balaji Fresh Market
    (2, 0, 38, 80), (2, 1, 12, 50), (2, 2, 32, 70),
    (2, 3, 55, 15), (2, 7, 440, 8), (2, 8, 278, 10),
    (2, 10, 272, 12),
]


async def seed() -> None:  # noqa: C901
    print("\nKhana Bazaar — Seeding Database\n")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    async with AsyncSession(engine) as session:

        print("1  Inserting users ...")
        db_users: list[User] = []
        for u in TEST_USERS:
            existing = await session.exec(select(User).where(User.email == u["email"]))
            user = existing.first()
            if user:
                print(f"  already exists: {u['email']}")
                db_users.append(user)
            else:
                user = User(
                    email=u["email"],
                    full_name=u["display_name"],
                    role=u["role"],
                    is_active=True,
                )
                session.add(user)
                await session.flush()
                print(f"  created: {u['email']} (id={user.id}, role={user.role.value})")
                db_users.append(user)

        print("\n2  Inserting categories ...")
        cat_ids: list[int] = []
        for c in CATEGORIES:
            existing = await session.exec(select(Category).where(Category.name == c["name"]))
            cat = existing.first()
            if cat:
                assert cat.id is not None
                cat_ids.append(cat.id)
            else:
                cat = Category(name=c["name"], description=c["description"])
                session.add(cat)
                await session.flush()
                assert cat.id is not None
                cat_ids.append(cat.id)
                print(f"  created: {c['name']}")

        print("\n3  Inserting products ...")
        product_ids: list[int] = []
        for p in PRODUCTS:
            existing = await session.exec(select(MasterProduct).where(MasterProduct.name == p["name"]))
            prod = existing.first()
            if prod:
                assert prod.id is not None
                product_ids.append(prod.id)
            else:
                prod = MasterProduct(
                    name=p["name"],
                    description=p["description"],
                    category_id=cat_ids[p["category_idx"]],
                    image_url=p["image_url"],
                    base_price=p["base_price"],
                )
                session.add(prod)
                await session.flush()
                assert prod.id is not None
                product_ids.append(prod.id)
                print(f"  created: {p['name']}")

        print("\n4  Inserting stores ...")
        store_ids: list[int] = []
        for s in STORES:
            seller = db_users[s["seller_idx"]]
            assert seller.id is not None
            existing = await session.exec(select(Store).where(Store.name == s["name"]))
            store = existing.first()
            if store:
                assert store.id is not None
                store_ids.append(store.id)
            else:
                store = Store(
                    name=s["name"],
                    seller_id=seller.id,
                    is_active=True,
                    **{k: s[k] for k in _ADDRESS_KEYS},
                )
                session.add(store)
                await session.flush()
                assert store.id is not None
                store_ids.append(store.id)
                print(f"  created: {s['name']}")

        print("\n5  Inserting inventory ...")
        for store_idx, prod_idx, price, stock in INVENTORIES:
            sid = store_ids[store_idx]
            pid = product_ids[prod_idx]
            existing = await session.exec(
                select(StoreInventory).where(
                    StoreInventory.store_id == sid,
                    StoreInventory.product_id == pid,
                )
            )
            if not existing.first():
                inv = StoreInventory(store_id=sid, product_id=pid, price=price, stock=stock, is_available=stock > 0)
                session.add(inv)

        await session.commit()

    await engine.dispose()

    print("\nSeeding complete!\n")
    print("Test accounts (login via email OTP):")
    print(f"{'Role':<10} {'Email':<32}")
    print("-" * 44)
    for u in TEST_USERS:
        print(f"{u['role'].value:<10} {u['email']:<32}")


if __name__ == "__main__":
    asyncio.run(seed())
