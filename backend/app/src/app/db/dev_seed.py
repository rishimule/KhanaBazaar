from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import User, UserRole
from app.models.catalog import Category, MasterProduct
from app.models.seller import SellerProfile, VerificationStatus
from app.models.store import Store, StoreInventory

TEST_USERS = [
    {"email": "admin@khanabazaar.dev", "display_name": "Platform Admin", "role": UserRole.Admin},
    {"email": "seller@khanabazaar.dev", "display_name": "Ravi Sharma", "role": UserRole.Seller},
    {"email": "seller2@khanabazaar.dev", "display_name": "Krishna Patel", "role": UserRole.Seller},
    {"email": "seller3@khanabazaar.dev", "display_name": "Balaji Ramaswamy", "role": UserRole.Seller},
    {"email": "customer@khanabazaar.dev", "display_name": "Priya Verma", "role": UserRole.Customer},
]

ADMIN = {
    "email": "admin@khanabazaar.dev",
    "full_name": "Platform Admin",
    "role": UserRole.Admin,
}

APPLICATIONS = [
    {
        "email": "pending.seller@khanabazaar.dev",
        "full_name": "Arjun Menon",
        "business_name": "Arjun Fresh Kirana",
        "business_category": "Groceries",
        "address_line1": "221B, Carter Road",
        "address_line2": "Bandra West",
        "landmark": "Near Bandstand Promenade",
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400050",
        "country": "India",
        "latitude": None,
        "longitude": None,
        "phone": "+919812345670",
        "gst_number": "27ABCDE1234F1Z5",
        "fssai_license": "11223344556677",
        "bank_account_number": "50100200300400",
        "bank_ifsc": "HDFC0001234",
        "status": VerificationStatus.Pending,
        "rejection_reason": None,
    },
    {
        "email": "approved.seller@khanabazaar.dev",
        "full_name": "Sana Kapoor",
        "business_name": "Sana Organic Mart",
        "business_category": "Organic Produce",
        "address_line1": "14, Brigade Road",
        "address_line2": "Ashok Nagar",
        "landmark": "Opposite Cauvery Emporium",
        "city": "Bengaluru",
        "state": "Karnataka",
        "pincode": "560001",
        "country": "India",
        "latitude": None,
        "longitude": None,
        "phone": "+919812345671",
        "gst_number": "29FGHIJ5678K2Z6",
        "fssai_license": "22334455667788",
        "bank_account_number": "60100200300500",
        "bank_ifsc": "ICIC0005678",
        "status": VerificationStatus.Approved,
        "rejection_reason": None,
    },
    {
        "email": "rejected.seller@khanabazaar.dev",
        "full_name": "Vikram Singh",
        "business_name": "Vikram Provision Store",
        "business_category": "Groceries",
        "address_line1": "7, Sector 18",
        "address_line2": None,
        "landmark": "Near Atta Market",
        "city": "Noida",
        "state": "Uttar Pradesh",
        "pincode": "201301",
        "country": "India",
        "latitude": None,
        "longitude": None,
        "phone": "+919812345672",
        "gst_number": "09KLMNO9012P3Z7",
        "fssai_license": "33445566778899",
        "bank_account_number": "70100200300600",
        "bank_ifsc": "SBIN0009012",
        "status": VerificationStatus.Rejected,
        "rejection_reason": "GST number does not match business address on record. Please update and resubmit.",
    },
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

_STORES_BY_NAME = {store["name"]: store for store in STORES}
STORE_ITEMS = [
    {
        **store,
        "seller_email": TEST_USERS[store["seller_idx"]]["email"],
    }
    for store in STORES
]

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

INVENTORY_ITEMS = [
    {
        "store_name": STORES[store_idx]["name"],
        "product_name": PRODUCTS[product_idx]["name"],
        "category_name": CATEGORIES[PRODUCTS[product_idx]["category_idx"]]["name"],
        "price": price,
        "stock": stock,
    }
    for store_idx, product_idx, price, stock in INVENTORIES
]

STORE_OWNER_PROFILES = [
    {
        "email": "seller@khanabazaar.dev",
        "full_name": "Ravi Sharma",
        "business_name": "Sharma General Store",
        "business_category": "Groceries",
        "phone": "+919811110001",
        "gst_number": "06AAAAA1111A1Z1",
        "fssai_license": "44556677889900",
        "bank_account_number": "80100200300700",
        "bank_ifsc": "HDFC0000001",
        "status": VerificationStatus.Approved,
        "rejection_reason": None,
        **{key: _STORES_BY_NAME["Sharma General Store"][key] for key in _ADDRESS_KEYS},
    },
    {
        "email": "seller2@khanabazaar.dev",
        "full_name": "Krishna Patel",
        "business_name": "Krishna Supermart",
        "business_category": "Groceries",
        "phone": "+919811110002",
        "gst_number": "27BBBBB2222B2Z2",
        "fssai_license": "55667788990011",
        "bank_account_number": "90100200300800",
        "bank_ifsc": "ICIC0000002",
        "status": VerificationStatus.Approved,
        "rejection_reason": None,
        **{key: _STORES_BY_NAME["Krishna Supermart"][key] for key in _ADDRESS_KEYS},
    },
    {
        "email": "seller3@khanabazaar.dev",
        "full_name": "Balaji Ramaswamy",
        "business_name": "Balaji Fresh Market",
        "business_category": "Fresh Produce",
        "phone": "+919811110003",
        "gst_number": "33CCCCC3333C3Z3",
        "fssai_license": "66778899001122",
        "bank_account_number": "00100200300900",
        "bank_ifsc": "SBIN0000003",
        "status": VerificationStatus.Approved,
        "rejection_reason": None,
        **{key: _STORES_BY_NAME["Balaji Fresh Market"][key] for key in _ADDRESS_KEYS},
    },
]

EXPECTED_FULL_COUNTS = {
    "users": 8,
    "sellerprofile": 6,
    "category": 4,
    "masterproduct": 12,
    "store": 3,
    "storeinventory": 26,
}


async def _upsert_user(session: AsyncSession, email: str, full_name: str, role: UserRole) -> User:
    existing = await session.exec(select(User).where(User.email == email))
    user = existing.first()
    if user is None:
        user = User(email=email, full_name=full_name, role=role, is_active=True)
    else:
        user.full_name = full_name
        user.role = role
        user.is_active = True
    session.add(user)
    await session.flush()
    return user


async def _upsert_profile(session: AsyncSession, user: User, data: Mapping[str, Any]) -> SellerProfile:
    assert user.id is not None
    existing = await session.exec(select(SellerProfile).where(SellerProfile.user_id == user.id))
    profile = existing.first()
    profile_fields = {
        "business_name": data["business_name"],
        "business_category": data["business_category"],
        "phone": data["phone"],
        "gst_number": data["gst_number"],
        "fssai_license": data["fssai_license"],
        "bank_account_number": data["bank_account_number"],
        "bank_ifsc": data["bank_ifsc"],
        "verification_status": data["status"],
        "rejection_reason": data["rejection_reason"],
        **{key: data[key] for key in _ADDRESS_KEYS},
    }
    if profile is None:
        profile = SellerProfile(user_id=user.id, **profile_fields)
    else:
        for key, value in profile_fields.items():
            setattr(profile, key, value)
    session.add(profile)
    await session.flush()
    return profile


async def _upsert_category(session: AsyncSession, data: Mapping[str, Any]) -> Category:
    existing = await session.exec(select(Category).where(Category.name == data["name"]))
    category = existing.first()
    if category is None:
        category = Category(name=data["name"], description=data["description"])
    else:
        category.description = data["description"]
    session.add(category)
    await session.flush()
    return category


async def _upsert_product(
    session: AsyncSession,
    data: Mapping[str, Any],
    category_id: int,
) -> MasterProduct:
    existing = await session.exec(
        select(MasterProduct).where(
            MasterProduct.name == data["name"],
            MasterProduct.category_id == category_id,
        )
    )
    product = existing.first()
    product_fields = {
        "description": data["description"],
        "category_id": category_id,
        "image_url": data["image_url"],
        "base_price": data["base_price"],
    }
    if product is None:
        product = MasterProduct(name=data["name"], **product_fields)
    else:
        for key, value in product_fields.items():
            setattr(product, key, value)
    session.add(product)
    await session.flush()
    return product


async def _upsert_store(session: AsyncSession, data: Mapping[str, Any], seller_id: int) -> Store:
    existing = await session.exec(
        select(Store).where(
            Store.name == data["name"],
            Store.seller_id == seller_id,
        )
    )
    store = existing.first()
    store_fields = {
        "seller_id": seller_id,
        "is_active": True,
        **{key: data[key] for key in _ADDRESS_KEYS},
    }
    if store is None:
        store = Store(name=data["name"], **store_fields)
    else:
        for key, value in store_fields.items():
            setattr(store, key, value)
    session.add(store)
    await session.flush()
    return store


async def _upsert_inventory(
    session: AsyncSession,
    store_id: int,
    product_id: int,
    price: float,
    stock: int,
) -> StoreInventory:
    existing = await session.exec(
        select(StoreInventory).where(
            StoreInventory.store_id == store_id,
            StoreInventory.product_id == product_id,
        )
    )
    inventory = existing.first()
    inventory_fields = {
        "price": price,
        "stock": stock,
        "is_available": stock > 0,
    }
    if inventory is None:
        inventory = StoreInventory(store_id=store_id, product_id=product_id, **inventory_fields)
    else:
        for key, value in inventory_fields.items():
            setattr(inventory, key, value)
    session.add(inventory)
    await session.flush()
    return inventory


async def seed_seller_application_subset(session: AsyncSession) -> None:
    await _upsert_user(session, ADMIN["email"], ADMIN["full_name"], ADMIN["role"])
    for application in APPLICATIONS:
        user = await _upsert_user(
            session,
            application["email"],
            application["full_name"],
            UserRole.Seller,
        )
        await _upsert_profile(session, user, application)


async def seed_demo_data(session: AsyncSession) -> None:
    users_by_email: dict[str, User] = {}
    for user_data in TEST_USERS:
        user = await _upsert_user(
            session,
            user_data["email"],
            user_data["display_name"],
            user_data["role"],
        )
        users_by_email[user.email] = user

    for profile_data in STORE_OWNER_PROFILES:
        user = users_by_email[profile_data["email"]]
        await _upsert_profile(session, user, profile_data)

    for application in APPLICATIONS:
        user = await _upsert_user(
            session,
            application["email"],
            application["full_name"],
            UserRole.Seller,
        )
        users_by_email[user.email] = user
        await _upsert_profile(session, user, application)

    categories_by_name: dict[str, Category] = {}
    for category_data in CATEGORIES:
        category = await _upsert_category(session, category_data)
        categories_by_name[category.name] = category

    products_by_key: dict[tuple[str, str], MasterProduct] = {}
    for product_data in PRODUCTS:
        category = categories_by_name[CATEGORIES[product_data["category_idx"]]["name"]]
        assert category.id is not None
        product = await _upsert_product(session, product_data, category.id)
        products_by_key[(category.name, product.name)] = product

    stores_by_name: dict[str, Store] = {}
    for store_data in STORE_ITEMS:
        user = users_by_email[store_data["seller_email"]]
        assert user.id is not None
        store = await _upsert_store(session, store_data, user.id)
        stores_by_name[store.name] = store

    for inventory_item in INVENTORY_ITEMS:
        store = stores_by_name[inventory_item["store_name"]]
        product = products_by_key[
            (inventory_item["category_name"], inventory_item["product_name"])
        ]
        assert store.id is not None
        assert product.id is not None
        await _upsert_inventory(
            session,
            store.id,
            product.id,
            inventory_item["price"],
            inventory_item["stock"],
        )

    await verify_expected_counts(session)


async def get_seed_counts(session: AsyncSession) -> dict[str, int]:
    counts = {}
    models = {
        "users": User,
        "sellerprofile": SellerProfile,
        "category": Category,
        "masterproduct": MasterProduct,
        "store": Store,
        "storeinventory": StoreInventory,
    }
    for key, model in models.items():
        result = await session.exec(select(func.count()).select_from(model))
        counts[key] = int(result.one())
    return counts


async def verify_expected_counts(session: AsyncSession) -> dict[str, int]:
    counts = await get_seed_counts(session)
    if counts != EXPECTED_FULL_COUNTS:
        raise ValueError(
            f"Seed counts mismatch: expected {EXPECTED_FULL_COUNTS}, got {counts}"
        )
    return counts
