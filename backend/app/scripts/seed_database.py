#!/usr/bin/env python3
"""
Khana Bazaar — Database Seed Script
====================================
Creates Firebase Auth test users and populates PostgreSQL with
categories, products, stores, and inventory that match the
frontend mock-data.ts exactly.

Usage (from backend/app/):
    PYTHONPATH=src uv run python scripts/seed_database.py
"""

import asyncio
import os
import sys

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import firebase_admin
from firebase_admin import auth, credentials
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.base import User, UserRole
from app.models.catalog import Category, MasterProduct
from app.models.store import Store, StoreInventory


# ─── Firebase setup ──────────────────────────────────────────

def init_firebase() -> None:
    if firebase_admin._apps:
        return
    cred_path = settings.GOOGLE_APPLICATION_CREDENTIALS
    if cred_path and os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {"projectId": settings.FIREBASE_PROJECT_ID})
    else:
        firebase_admin.initialize_app(options={"projectId": settings.FIREBASE_PROJECT_ID})


def get_or_create_firebase_user(email: str, password: str, display_name: str) -> str:
    """Create a Firebase Auth user or return the UID of an existing one."""
    try:
        fb_user = auth.get_user_by_email(email)
        print(f"  ✓ Firebase user already exists: {email} (uid={fb_user.uid})")
        return fb_user.uid
    except auth.UserNotFoundError:
        fb_user = auth.create_user(
            email=email,
            password=password,
            display_name=display_name,
            email_verified=True,
        )
        print(f"  ✓ Created Firebase user: {email} (uid={fb_user.uid})")
        return fb_user.uid


# ─── Test accounts ───────────────────────────────────────────

TEST_USERS = [
    {"email": "admin@khanabazaar.dev", "password": "Test@12345", "display_name": "Platform Admin", "role": UserRole.Admin},
    {"email": "seller@khanabazaar.dev", "password": "Test@12345", "display_name": "Ravi Sharma", "role": UserRole.Seller},
    {"email": "seller2@khanabazaar.dev", "password": "Test@12345", "display_name": "Krishna Patel", "role": UserRole.Seller},
    {"email": "seller3@khanabazaar.dev", "password": "Test@12345", "display_name": "Balaji Ramaswamy", "role": UserRole.Seller},
    {"email": "customer@khanabazaar.dev", "password": "Test@12345", "display_name": "Priya Verma", "role": UserRole.Customer},
]


# ─── Seed data (mirrors mock-data.ts) ────────────────────────

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
    {"name": "Sharma General Store", "address": "12, MG Road, Sector 14, Gurugram, Haryana 122001", "seller_idx": 1},
    {"name": "Krishna Supermart", "address": "45, Nehru Nagar, Andheri West, Mumbai, Maharashtra 400058", "seller_idx": 2},
    {"name": "Balaji Fresh Market", "address": "78, Rajaji Street, T. Nagar, Chennai, Tamil Nadu 600017", "seller_idx": 3},
]

# Inventory: (store_idx, product_idx, price, stock)
INVENTORIES = [
    # Sharma General Store — has almost everything
    (0, 0, 42, 50), (0, 1, 18, 30), (0, 2, 38, 60),
    (0, 3, 56, 20), (0, 4, 95, 15),
    (0, 6, 165, 25), (0, 7, 460, 10), (0, 8, 285, 12),
    (0, 9, 20, 100), (0, 10, 275, 18), (0, 11, 82, 40),
    # Krishna Supermart — dairy-heavy
    (1, 0, 45, 40), (1, 3, 54, 35), (1, 4, 92, 20),
    (1, 5, 48, 25), (1, 6, 158, 30),
    (1, 9, 20, 60), (1, 10, 268, 15), (1, 11, 78, 50),
    # Balaji Fresh Market — produce-focused
    (2, 0, 38, 80), (2, 1, 12, 50), (2, 2, 32, 70),
    (2, 3, 55, 15), (2, 7, 440, 8), (2, 8, 278, 10),
    (2, 10, 272, 12),
]


# ─── Main ────────────────────────────────────────────────────

async def seed() -> None:
    print("\n🌱 Khana Bazaar — Seeding Database\n")

    # 1. Firebase users
    print("1️⃣  Creating Firebase Auth users …")
    init_firebase()
    firebase_uids: list[str] = []
    for u in TEST_USERS:
        uid = get_or_create_firebase_user(u["email"], u["password"], u["display_name"])
        firebase_uids.append(uid)

    # 2. Database
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with AsyncSession(engine) as session:

        # -- Users --
        print("\n2️⃣  Inserting database users …")
        db_users: list[User] = []
        for i, u in enumerate(TEST_USERS):
            existing = await session.exec(
                select(User).where(User.firebase_uid == firebase_uids[i])
            )
            user = existing.first()
            if user:
                print(f"  ✓ User already exists: {u['email']}")
                db_users.append(user)
            else:
                user = User(
                    firebase_uid=firebase_uids[i],
                    email=u["email"],
                    full_name=u["display_name"],
                    role=u["role"],
                    is_active=True,
                )
                session.add(user)
                await session.flush()
                print(f"  ✓ Created user: {u['email']} (id={user.id}, role={user.role.value})")
                db_users.append(user)

        # -- Categories --
        print("\n3️⃣  Inserting categories …")
        cat_ids: list[int] = []
        for c in CATEGORIES:
            existing = await session.exec(
                select(Category).where(Category.name == c["name"])
            )
            cat = existing.first()
            if cat:
                print(f"  ✓ Category exists: {c['name']} (id={cat.id})")
                assert cat.id is not None
                cat_ids.append(cat.id)
            else:
                cat = Category(name=c["name"], description=c["description"])
                session.add(cat)
                await session.flush()
                assert cat.id is not None
                print(f"  ✓ Created: {c['name']} (id={cat.id})")
                cat_ids.append(cat.id)

        # -- Products --
        print("\n4️⃣  Inserting master products …")
        product_ids: list[int] = []
        for p in PRODUCTS:
            existing = await session.exec(
                select(MasterProduct).where(MasterProduct.name == p["name"])
            )
            prod = existing.first()
            if prod:
                print(f"  ✓ Product exists: {p['name']} (id={prod.id})")
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
                print(f"  ✓ Created: {p['name']} (id={prod.id})")
                product_ids.append(prod.id)

        # -- Stores --
        print("\n5️⃣  Inserting stores …")
        store_ids: list[int] = []
        for s in STORES:
            seller = db_users[s["seller_idx"]]
            assert seller.id is not None
            existing = await session.exec(
                select(Store).where(Store.name == s["name"])
            )
            store = existing.first()
            if store:
                print(f"  ✓ Store exists: {s['name']} (id={store.id})")
                assert store.id is not None
                store_ids.append(store.id)
            else:
                store = Store(
                    name=s["name"],
                    address=s["address"],
                    seller_id=seller.id,
                    is_active=True,
                )
                session.add(store)
                await session.flush()
                assert store.id is not None
                print(f"  ✓ Created: {s['name']} (id={store.id}, seller_id={seller.id})")
                store_ids.append(store.id)

        # -- Inventory --
        print("\n6️⃣  Inserting store inventories …")
        for store_idx, prod_idx, price, stock in INVENTORIES:
            sid = store_ids[store_idx]
            pid = product_ids[prod_idx]
            existing = await session.exec(
                select(StoreInventory).where(
                    StoreInventory.store_id == sid,
                    StoreInventory.product_id == pid,
                )
            )
            if existing.first():
                print(f"  ✓ Inventory exists: store={sid}, product={pid}")
            else:
                inv = StoreInventory(
                    store_id=sid,
                    product_id=pid,
                    price=price,
                    stock=stock,
                    is_available=stock > 0,
                )
                session.add(inv)
                await session.flush()
                print(f"  ✓ Added: store={sid}, product={pid}, price=₹{price}, stock={stock}")

        await session.commit()

    await engine.dispose()

    print("\n✅ Seeding complete!\n")
    print("Test accounts:")
    print("┌─────────┬──────────────────────────────┬─────────────┐")
    print("│ Role    │ Email                        │ Password    │")
    print("├─────────┼──────────────────────────────┼─────────────┤")
    for u in TEST_USERS:
        print(f"│ {u['role'].value:<7} │ {u['email']:<28} │ {u['password']:<11} │")
    print("└─────────┴──────────────────────────────┴─────────────┘")


if __name__ == "__main__":
    asyncio.run(seed())
