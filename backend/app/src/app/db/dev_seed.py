from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import (
    Category,
    CategoryTranslation,
    Language,
    MasterProduct,
    MasterProductTranslation,
    Service,
    ServiceTranslation,
    Subcategory,
    SubcategoryTranslation,
)
from app.models.profile import (
    AdminProfile,
    CustomerProfile,
    SellerProfile,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from app.services.profiles import split_full_name

LANGUAGES = [
    ("en", "English", "English"),
    ("hi", "Hindi", "हिन्दी"),
    ("mr", "Marathi", "मराठी"),
    ("gu", "Gujarati", "ગુજરાતી"),
    ("pa", "Punjabi", "ਪੰਜਾਬੀ"),
]

SERVICES: list[dict[str, Any]] = [
    {"slug": "grocery", "name": "Grocery", "description": "Daily essentials, fresh produce, pantry staples"},
    {"slug": "electronics", "name": "Electronics", "description": "Gadgets, accessories, and home electronics"},
    {"slug": "pharmacy", "name": "Pharmacy", "description": "Medicines, wellness, and personal care"},
]
DEFAULT_SUBCATEGORY_SLUG = "_default"

TEST_USERS: list[dict[str, Any]] = [
    {"email": "admin@khanabazaar.dev", "display_name": "Platform Admin", "role": UserRole.Admin},
    {"email": "seller@khanabazaar.dev", "display_name": "Ravi Sharma", "role": UserRole.Seller},
    {"email": "seller2@khanabazaar.dev", "display_name": "Krishna Patel", "role": UserRole.Seller},
    {"email": "seller3@khanabazaar.dev", "display_name": "Balaji Ramaswamy", "role": UserRole.Seller},
    {"email": "customer@khanabazaar.dev", "display_name": "Priya Verma", "role": UserRole.Customer},
]

ADMIN: dict[str, Any] = {
    "email": "admin@khanabazaar.dev",
    "full_name": "Platform Admin",
    "role": UserRole.Admin,
    "phone": "+919811110100",
    "employee_code": "KB-ADMIN-001",
    "department": "Platform",
}

CUSTOMER: dict[str, Any] = {
    "email": "customer@khanabazaar.dev",
    "full_name": "Priya Verma",
    "phone": "+919811110200",
}

APPLICATIONS: list[dict[str, Any]] = [
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

CATEGORIES: list[dict[str, Any]] = [
    {"service_slug": "grocery", "slug": "fruits-vegetables", "name": "Fruits & Vegetables", "description": "Fresh produce from local farms"},
    {"service_slug": "grocery", "slug": "dairy-bakery", "name": "Dairy & Bakery", "description": "Milk, paneer, bread, and baked goods"},
    {"service_slug": "grocery", "slug": "staples-grains", "name": "Staples & Grains", "description": "Rice, atta, dal, and cooking essentials"},
    {"service_slug": "grocery", "slug": "snacks-beverages", "name": "Snacks & Beverages", "description": "Chips, biscuits, tea, coffee, and cold drinks"},
]

PRODUCTS: list[dict[str, Any]] = [
    {"slug": "fresh-tomatoes", "name": "Fresh Tomatoes", "description": "Firm, red tomatoes — perfect for curries and chutneys", "category_idx": 0, "image_url": "/images/products/tomatoes.jpg", "base_price": 40},
    {"slug": "green-coriander-bunch", "name": "Green Coriander Bunch", "description": "Fresh dhania for garnishing and chutney", "category_idx": 0, "image_url": "/images/products/coriander.jpg", "base_price": 15},
    {"slug": "onions-pyaaz", "name": "Onions (Pyaaz)", "description": "Medium-sized onions, a kitchen staple", "category_idx": 0, "image_url": "/images/products/onions.jpg", "base_price": 35},
    {"slug": "amul-taza-milk-1l", "name": "Amul Taza Milk (1L)", "description": "Toned milk, pasteurized & homogenized", "category_idx": 1, "image_url": "/images/products/milk.jpg", "base_price": 54},
    {"slug": "amul-paneer-200g", "name": "Amul Paneer (200g)", "description": "Fresh cottage cheese block for sabzi & tikka", "category_idx": 1, "image_url": "/images/products/paneer.jpg", "base_price": 90},
    {"slug": "britannia-bread-400g", "name": "Britannia Bread (400g)", "description": "Soft white sandwich bread", "category_idx": 1, "image_url": "/images/products/bread.jpg", "base_price": 45},
    {"slug": "toor-dal-1kg", "name": "Toor Dal (1kg)", "description": "Premium quality arhar dal for everyday cooking", "category_idx": 2, "image_url": "/images/products/toor-dal.jpg", "base_price": 160},
    {"slug": "basmati-rice-5kg", "name": "Basmati Rice (5kg)", "description": "Long grain aged basmati — perfect for biryani", "category_idx": 2, "image_url": "/images/products/rice.jpg", "base_price": 450},
    {"slug": "aashirvaad-atta-5kg", "name": "Aashirvaad Atta (5kg)", "description": "Whole wheat flour for soft rotis", "category_idx": 2, "image_url": "/images/products/atta.jpg", "base_price": 280},
    {"slug": "lays-classic-salted-52g", "name": "Lay's Classic Salted (52g)", "description": "Crispy potato chips, classic flavor", "category_idx": 3, "image_url": "/images/products/lays.jpg", "base_price": 20},
    {"slug": "tata-tea-gold-500g", "name": "Tata Tea Gold (500g)", "description": "Premium blend of Assam & Darjeeling tea", "category_idx": 3, "image_url": "/images/products/tea.jpg", "base_price": 270},
    {"slug": "parle-g-biscuits-800g", "name": "Parle-G Biscuits (800g)", "description": "India's iconic glucose biscuits — since 1939", "category_idx": 3, "image_url": "/images/products/parle-g.jpg", "base_price": 80},
]

STORES: list[dict[str, Any]] = [
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
        "product_slug": PRODUCTS[product_idx]["slug"],
        "price": price,
        "stock": stock,
    }
    for store_idx, product_idx, price, stock in INVENTORIES
]

STORE_OWNER_PROFILES: list[dict[str, Any]] = [
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
    "language": 5,
    "customerprofile": 1,
    "adminprofile": 1,
    "sellerprofile": 6,
    "address": 9,
    "service": 3,
    "service_translation": 3,
    "category": 4,
    "category_translation": 4,
    "subcategory": 4,
    "subcategory_translation": 4,
    "masterproduct": 12,
    "masterproduct_translation": 12,
    "store": 3,
    "storeinventory": 26,
}


def get_canonical_login_email_rows() -> list[tuple[str, str]]:
    rows = [(user["role"].value, user["email"]) for user in TEST_USERS]
    rows.extend(("seller", application["email"]) for application in APPLICATIONS)
    return rows


def get_seller_application_subset_login_email_rows() -> list[tuple[str, str]]:
    return [("admin", ADMIN["email"]), *[("seller", application["email"]) for application in APPLICATIONS]]


async def _upsert_language(
    session: AsyncSession, code: str, name: str, native_name: str
) -> Language:
    existing = await session.get(Language, code)
    if existing is None:
        language = Language(code=code, name=name, native_name=native_name, is_active=True)
        session.add(language)
        await session.flush()
        return language
    existing.name = name
    existing.native_name = native_name
    existing.is_active = True
    session.add(existing)
    await session.flush()
    return existing


async def _ensure_languages(session: AsyncSession) -> None:
    for code, name, native in LANGUAGES:
        await _upsert_language(session, code, name, native)


async def _upsert_user(
    session: AsyncSession, email: str, role: UserRole
) -> User:
    existing = await session.exec(select(User).where(User.email == email))
    user = existing.first()
    if user is None:
        user = User(email=email, role=role, is_active=True, preferred_language="en")
    else:
        user.role = role
        user.is_active = True
    session.add(user)
    await session.flush()
    return user


async def _upsert_address(session: AsyncSession, owner: object | None, data: Mapping[str, Any]) -> Address:
    """Update existing owner-linked address, or insert a new one."""
    address_fields = {key: data[key] for key in _ADDRESS_KEYS}
    if owner is not None:
        for key, value in address_fields.items():
            setattr(owner, key, value)
        session.add(owner)
        await session.flush()
        return owner  # type: ignore[return-value]
    address = Address(**address_fields)
    session.add(address)
    await session.flush()
    return address


async def _upsert_seller_profile(
    session: AsyncSession, user: User, data: Mapping[str, Any]
) -> SellerProfile:
    assert user.id is not None
    existing = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == user.id)
    )
    profile = existing.first()
    first_name, last_name = split_full_name(data["full_name"])
    if profile is None:
        address = await _upsert_address(session, None, data)
        profile = SellerProfile(
            user_id=user.id,
            first_name=first_name,
            last_name=last_name,
            phone=data["phone"],
            business_name=data["business_name"],
            business_category=data["business_category"],
            gst_number=data["gst_number"],
            fssai_license=data["fssai_license"],
            bank_account_number=data["bank_account_number"],
            bank_ifsc=data["bank_ifsc"],
            verification_status=data["status"],
            rejection_reason=data["rejection_reason"],
            business_address_id=address.id,
        )
    else:
        existing_address = await session.get(Address, profile.business_address_id)
        await _upsert_address(session, existing_address, data)
        profile.first_name = first_name
        profile.last_name = last_name
        profile.phone = data["phone"]
        profile.business_name = data["business_name"]
        profile.business_category = data["business_category"]
        profile.gst_number = data["gst_number"]
        profile.fssai_license = data["fssai_license"]
        profile.bank_account_number = data["bank_account_number"]
        profile.bank_ifsc = data["bank_ifsc"]
        profile.verification_status = data["status"]
        profile.rejection_reason = data["rejection_reason"]
    session.add(profile)
    await session.flush()
    return profile


async def _upsert_admin_profile(
    session: AsyncSession, user: User, data: Mapping[str, Any]
) -> AdminProfile:
    assert user.id is not None
    existing = await session.exec(
        select(AdminProfile).where(AdminProfile.user_id == user.id)
    )
    profile = existing.first()
    first_name, last_name = split_full_name(data["full_name"])
    if profile is None:
        profile = AdminProfile(
            user_id=user.id,
            first_name=first_name,
            last_name=last_name,
            phone=data.get("phone"),
            employee_code=data.get("employee_code"),
            department=data.get("department"),
        )
    else:
        profile.first_name = first_name
        profile.last_name = last_name
        profile.phone = data.get("phone")
        profile.employee_code = data.get("employee_code")
        profile.department = data.get("department")
    session.add(profile)
    await session.flush()
    return profile


async def _upsert_customer_profile(
    session: AsyncSession, user: User, data: Mapping[str, Any]
) -> CustomerProfile:
    assert user.id is not None
    existing = await session.exec(
        select(CustomerProfile).where(CustomerProfile.user_id == user.id)
    )
    profile = existing.first()
    first_name, last_name = split_full_name(data["full_name"])
    if profile is None:
        profile = CustomerProfile(
            user_id=user.id,
            first_name=first_name,
            last_name=last_name,
            phone=data.get("phone"),
        )
    else:
        profile.first_name = first_name
        profile.last_name = last_name
        profile.phone = data.get("phone")
    session.add(profile)
    await session.flush()
    return profile


async def _ensure_service(
    session: AsyncSession, data: Mapping[str, Any], sort_order: int
) -> Service:
    result = await session.exec(select(Service).where(Service.slug == data["slug"]))
    service = result.first()
    if service is None:
        service = Service(slug=data["slug"], is_active=True, sort_order=sort_order)
        session.add(service)
        await session.flush()
    else:
        service.sort_order = sort_order
        service.is_active = True
        session.add(service)
        await session.flush()

    translation_result = await session.exec(
        select(ServiceTranslation).where(
            ServiceTranslation.service_id == service.id,
            ServiceTranslation.language_code == "en",
        )
    )
    translation = translation_result.first()
    if translation is None:
        session.add(
            ServiceTranslation(
                service_id=service.id,
                language_code="en",
                name=data["name"],
                description=data.get("description"),
            )
        )
    else:
        translation.name = data["name"]
        translation.description = data.get("description")
    await session.flush()
    return service


async def _upsert_category(
    session: AsyncSession, service_id: int, data: Mapping[str, Any], sort_order: int
) -> Category:
    result = await session.exec(
        select(Category).where(
            Category.service_id == service_id,
            Category.slug == data["slug"],
        )
    )
    category = result.first()
    if category is None:
        category = Category(service_id=service_id, slug=data["slug"], sort_order=sort_order)
    else:
        category.sort_order = sort_order
    session.add(category)
    await session.flush()

    translation_result = await session.exec(
        select(CategoryTranslation).where(
            CategoryTranslation.category_id == category.id,
            CategoryTranslation.language_code == "en",
        )
    )
    translation = translation_result.first()
    if translation is None:
        session.add(
            CategoryTranslation(
                category_id=category.id,
                language_code="en",
                name=data["name"],
                description=data["description"],
            )
        )
    else:
        translation.name = data["name"]
        translation.description = data["description"]
    await session.flush()
    return category


async def _upsert_default_subcategory(
    session: AsyncSession, category: Category, name: str
) -> Subcategory:
    assert category.id is not None
    result = await session.exec(
        select(Subcategory).where(
            Subcategory.category_id == category.id,
            Subcategory.slug == DEFAULT_SUBCATEGORY_SLUG,
        )
    )
    sub = result.first()
    if sub is None:
        sub = Subcategory(
            category_id=category.id, slug=DEFAULT_SUBCATEGORY_SLUG, sort_order=0
        )
    session.add(sub)
    await session.flush()

    translation_result = await session.exec(
        select(SubcategoryTranslation).where(
            SubcategoryTranslation.subcategory_id == sub.id,
            SubcategoryTranslation.language_code == "en",
        )
    )
    translation = translation_result.first()
    if translation is None:
        session.add(
            SubcategoryTranslation(
                subcategory_id=sub.id,
                language_code="en",
                name=name,
                description=None,
            )
        )
    else:
        translation.name = name
    await session.flush()
    return sub


async def _upsert_product(
    session: AsyncSession, subcategory_id: int, data: Mapping[str, Any]
) -> MasterProduct:
    result = await session.exec(
        select(MasterProduct).where(MasterProduct.slug == data["slug"])
    )
    product = result.first()
    if product is None:
        product = MasterProduct(
            subcategory_id=subcategory_id,
            slug=data["slug"],
            image_url=data["image_url"],
            base_price=data["base_price"],
        )
    else:
        product.subcategory_id = subcategory_id
        product.image_url = data["image_url"]
        product.base_price = data["base_price"]
    session.add(product)
    await session.flush()

    translation_result = await session.exec(
        select(MasterProductTranslation).where(
            MasterProductTranslation.master_product_id == product.id,
            MasterProductTranslation.language_code == "en",
        )
    )
    translation = translation_result.first()
    if translation is None:
        session.add(
            MasterProductTranslation(
                master_product_id=product.id,
                language_code="en",
                name=data["name"],
                description=data["description"],
            )
        )
    else:
        translation.name = data["name"]
        translation.description = data["description"]
    await session.flush()
    return product


async def _upsert_store(
    session: AsyncSession, profile: SellerProfile, data: Mapping[str, Any]
) -> Store:
    assert profile.id is not None
    result = await session.exec(
        select(Store).where(
            Store.name == data["name"],
            Store.seller_profile_id == profile.id,
        )
    )
    store = result.first()
    if store is None:
        address = await _upsert_address(session, None, data)
        store = Store(
            name=data["name"],
            is_active=True,
            seller_profile_id=profile.id,
            address_id=address.id,
        )
    else:
        existing_address = await session.get(Address, store.address_id)
        await _upsert_address(session, existing_address, data)
        store.is_active = True
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
    result = await session.exec(
        select(StoreInventory).where(
            StoreInventory.store_id == store_id,
            StoreInventory.product_id == product_id,
        )
    )
    inventory = result.first()
    fields = {"price": price, "stock": stock, "is_available": stock > 0}
    if inventory is None:
        inventory = StoreInventory(store_id=store_id, product_id=product_id, **fields)
    else:
        for key, value in fields.items():
            setattr(inventory, key, value)
    session.add(inventory)
    await session.flush()
    return inventory


async def seed_seller_application_subset(session: AsyncSession) -> None:
    await _ensure_languages(session)
    admin_user = await _upsert_user(session, ADMIN["email"], ADMIN["role"])
    await _upsert_admin_profile(session, admin_user, ADMIN)
    for application in APPLICATIONS:
        user = await _upsert_user(session, application["email"], UserRole.Seller)
        await _upsert_seller_profile(session, user, application)


async def seed_demo_data(session: AsyncSession) -> None:
    await _ensure_languages(session)

    users_by_email: dict[str, User] = {}
    for user_data in TEST_USERS:
        user = await _upsert_user(session, user_data["email"], user_data["role"])
        users_by_email[user.email] = user

    await _upsert_admin_profile(session, users_by_email[ADMIN["email"]], ADMIN)
    await _upsert_customer_profile(session, users_by_email[CUSTOMER["email"]], CUSTOMER)

    for profile_data in STORE_OWNER_PROFILES:
        user = users_by_email[profile_data["email"]]
        await _upsert_seller_profile(session, user, profile_data)

    for application in APPLICATIONS:
        user = await _upsert_user(session, application["email"], UserRole.Seller)
        users_by_email[user.email] = user
        await _upsert_seller_profile(session, user, application)

    services_by_slug: dict[str, Service] = {}
    for sort_order, service_data in enumerate(SERVICES):
        service = await _ensure_service(session, service_data, sort_order)
        assert service.id is not None
        services_by_slug[service.slug] = service

    categories_by_slug: dict[str, Category] = {}
    subcategories_by_category_slug: dict[str, Subcategory] = {}
    for sort_order, category_data in enumerate(CATEGORIES):
        service = services_by_slug[category_data["service_slug"]]
        assert service.id is not None
        category = await _upsert_category(session, service.id, category_data, sort_order)
        categories_by_slug[category.slug] = category
        sub = await _upsert_default_subcategory(session, category, category_data["name"])
        subcategories_by_category_slug[category.slug] = sub

    products_by_slug: dict[str, MasterProduct] = {}
    for product_data in PRODUCTS:
        category = categories_by_slug[CATEGORIES[product_data["category_idx"]]["slug"]]
        sub = subcategories_by_category_slug[category.slug]
        assert sub.id is not None
        product = await _upsert_product(session, sub.id, product_data)
        products_by_slug[product.slug] = product

    stores_by_name: dict[str, Store] = {}
    for store_data in STORE_ITEMS:
        owner_user = users_by_email[store_data["seller_email"]]
        result = await session.exec(
            select(SellerProfile).where(SellerProfile.user_id == owner_user.id)
        )
        profile = result.first()
        assert profile is not None
        store = await _upsert_store(session, profile, store_data)
        stores_by_name[store.name] = store

    for inventory_item in INVENTORY_ITEMS:
        store = stores_by_name[inventory_item["store_name"]]
        product = products_by_slug[inventory_item["product_slug"]]
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


_COUNT_MODELS = {
    "users": User,
    "language": Language,
    "customerprofile": CustomerProfile,
    "adminprofile": AdminProfile,
    "sellerprofile": SellerProfile,
    "address": Address,
    "service": Service,
    "service_translation": ServiceTranslation,
    "category": Category,
    "category_translation": CategoryTranslation,
    "subcategory": Subcategory,
    "subcategory_translation": SubcategoryTranslation,
    "masterproduct": MasterProduct,
    "masterproduct_translation": MasterProductTranslation,
    "store": Store,
    "storeinventory": StoreInventory,
}


async def get_seed_counts(session: AsyncSession) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, model in _COUNT_MODELS.items():
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
