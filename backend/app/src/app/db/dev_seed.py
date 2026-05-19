# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db._dev_seed_data import (
    EXTRA_APPLICATIONS,
    EXTRA_CATEGORIES,
    EXTRA_CUSTOMERS,
    EXTRA_PRODUCTS,
    EXTRA_SERVICES,
    EXTRA_STORE_OWNER_PROFILES,
    EXTRA_STORES,
    EXTRA_SUBCATEGORIES,
    _image_for,
    generate_extra_inventories,
)
from app.models.address import Address, LocationSource
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
from app.models.commerce import (
    Delivery,
    DeliveryStatus,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.models.profile import (
    AdminProfile,
    CustomerAddress,
    CustomerProfile,
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from app.schemas.address import address_to_payload
from app.services.profiles import split_full_name
from app.utils.address import format_address
from app.utils.digipin import encode as digipin_encode

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
SERVICES.extend(EXTRA_SERVICES)
DEFAULT_SUBCATEGORY_SLUG = "_default"  # legacy, retained for catalog admin endpoints

TEST_USERS: list[dict[str, Any]] = [
    {"email": "admin@khanabazaar.dev", "display_name": "Platform Admin", "role": UserRole.Admin},
    {"email": "seller@khanabazaar.dev", "display_name": "Ravi Sharma", "role": UserRole.Seller},
    {"email": "seller2@khanabazaar.dev", "display_name": "Krishna Patel", "role": UserRole.Seller},
    {"email": "seller3@khanabazaar.dev", "display_name": "Balaji Ramaswamy", "role": UserRole.Seller},
    {"email": "seller4@khanabazaar.dev", "display_name": "Aditya Khanna", "role": UserRole.Seller},
    {"email": "seller5@khanabazaar.dev", "display_name": "Rahul Mehta", "role": UserRole.Seller},
    {"email": "seller6@khanabazaar.dev", "display_name": "Neha Iyer", "role": UserRole.Seller},
    {"email": "seller7@khanabazaar.dev", "display_name": "Anjali Gupta", "role": UserRole.Seller},
    {"email": "seller8@khanabazaar.dev", "display_name": "Suresh Reddy", "role": UserRole.Seller},
    {"email": "seller9@khanabazaar.dev", "display_name": "Pooja Bhatt", "role": UserRole.Seller},
]
# Append extra sellers BEFORE customers so STORE_ITEMS can index TEST_USERS by
# `seller_idx` (anchor stores use 1..9; generated stores use 10..90). Customers
# come after all sellers — order matters for the index-based store→seller link.
TEST_USERS.extend(
    {"email": owner["email"], "display_name": owner["full_name"], "role": UserRole.Seller}
    for owner in EXTRA_STORE_OWNER_PROFILES
)
TEST_USERS.append(
    {"email": "customer@khanabazaar.dev", "display_name": "Priya Verma", "role": UserRole.Customer},
)
TEST_USERS.extend(
    {"email": cust["email"], "display_name": cust["full_name"], "role": UserRole.Customer}
    for cust in EXTRA_CUSTOMERS
)

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
    # Five real Mumbai-area addresses baked at authoring time via
    # `scripts/bake_mumbai_seed.py` against the live /geo/reverse endpoint.
    # Coverage by store delivery radius (see STORES list below) is mixed
    # on purpose so manual QA exercises distance sort + serviceability gating.
    "addresses": [
        {
            "label": "Home", "is_default": True,
            "address_line1": "Shop No-1", "address_line2": "Bandra West",
            "landmark": None, "city": "Mumbai", "state": "Maharashtra",
            "pincode": "400050", "country": "India",
            "latitude": 19.0620132, "longitude": 72.8350166,
            "place_id": "ChIJ3a7_7hbJ5zsRTua0Lko4fWg",
            "location_source": "pin",
        },
        {
            "label": "Office", "is_default": False,
            "address_line1": "shop 462", "address_line2": "Lower Parel",
            "landmark": None, "city": "Mumbai", "state": "Maharashtra",
            "pincode": "400013", "country": "India",
            "latitude": 19.000969, "longitude": 72.8290959,
            "place_id": "ChIJj1DkqZjP5zsREIvsj3DfgyI",
            "location_source": "pin",
        },
        {
            "label": "Friend's Place", "is_default": False,
            "address_line1": "27", "address_line2": "Andheri East",
            "landmark": None, "city": "Mumbai", "state": "Maharashtra",
            "pincode": "400093", "country": "India",
            "latitude": 19.1220695, "longitude": 72.8700202,
            "place_id": "ChIJWyxqIs_J5zsRN14FDiaqRTI",
            "location_source": "pin",
        },
        {
            "label": "Parents", "is_default": False,
            "address_line1": "Main Building", "address_line2": "Powai",
            "landmark": None, "city": "Mumbai", "state": "Maharashtra",
            "pincode": "400076", "country": "India",
            "latitude": 19.1331093, "longitude": 72.91565440000001,
            "place_id": "ChIJ0egPbfbH5zsRi5n6M7ZV5yI",
            "location_source": "pin",
        },
        {
            "label": "Pune Trip", "is_default": False,
            "address_line1": "58", "address_line2": "Koregaon Park",
            "landmark": None, "city": "Pune", "state": "Maharashtra",
            "pincode": "411001", "country": "India",
            "latitude": 18.538646, "longitude": 73.892386,
            "place_id": "ChIJa9CQfQHBwjsRmqjG-A-aJ0A",
            "location_source": "pin",
        },
    ],
}

# Full customer roster: anchor Priya Verma first (keeps her at the same email
# the test suite asserts), then 9 generated customers.
CUSTOMERS: list[dict[str, Any]] = [CUSTOMER, *EXTRA_CUSTOMERS]

APPLICATIONS: list[dict[str, Any]] = [
    {
        "email": "pending.seller@khanabazaar.dev",
        "full_name": "Arjun Menon",
        "business_name": "Arjun Fresh Kirana",
        "service_slugs": ["grocery"],
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
        "service_slugs": ["grocery"],
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
        "service_slugs": ["grocery"],
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
APPLICATIONS.extend(EXTRA_APPLICATIONS)

CATEGORIES: list[dict[str, Any]] = [
    # Grocery
    {"service_slug": "grocery", "slug": "fruits-vegetables", "name": "Fruits & Vegetables", "description": "Fresh produce from local farms"},
    {"service_slug": "grocery", "slug": "dairy-bakery", "name": "Dairy & Bakery", "description": "Milk, paneer, bread, and baked goods"},
    {"service_slug": "grocery", "slug": "staples-grains", "name": "Staples & Grains", "description": "Rice, atta, dal, oils, and cooking essentials"},
    # Electronics
    {"service_slug": "electronics", "slug": "laptops-computers", "name": "Laptops & Computers", "description": "Notebooks, ultrabooks, and 2-in-1 convertibles"},
    {"service_slug": "electronics", "slug": "mobiles-tablets", "name": "Mobiles & Tablets", "description": "Smartphones, tablets, and wearables"},
    {"service_slug": "electronics", "slug": "audio-accessories", "name": "Audio & Accessories", "description": "Headphones, speakers, chargers and add-ons"},
    # Pharmacy
    {"service_slug": "pharmacy", "slug": "medicines", "name": "Medicines", "description": "OTC medicines for everyday ailments"},
    {"service_slug": "pharmacy", "slug": "personal-care", "name": "Personal Care", "description": "Oral care, skincare, and haircare essentials"},
    {"service_slug": "pharmacy", "slug": "wellness-nutrition", "name": "Wellness & Nutrition", "description": "Vitamins, protein powders, and herbal supplements"},
]
# Strip helper-only fields from extra categories before merging; _upsert_category
# only reads service_slug/slug/name/description.
CATEGORIES.extend(
    {k: v for k, v in cat.items() if k != "brand_pool"} for cat in EXTRA_CATEGORIES
)

SUBCATEGORIES: list[dict[str, Any]] = [
    # Grocery → Fruits & Vegetables
    {"category_slug": "fruits-vegetables", "slug": "leafy-greens", "name": "Leafy Greens", "description": "Spinach, methi, coriander, and other leafy bunches"},
    {"category_slug": "fruits-vegetables", "slug": "fresh-fruits", "name": "Fresh Fruits", "description": "Seasonal whole fruits"},
    {"category_slug": "fruits-vegetables", "slug": "everyday-vegetables", "name": "Everyday Vegetables", "description": "Tomatoes, onions, potatoes, and pantry vegetables"},
    # Grocery → Dairy & Bakery
    {"category_slug": "dairy-bakery", "slug": "milk-curd", "name": "Milk & Curd", "description": "Fresh milk, curd, and yogurt"},
    {"category_slug": "dairy-bakery", "slug": "cheese-paneer", "name": "Cheese & Paneer", "description": "Paneer, cheese slices, butter, and spreads"},
    {"category_slug": "dairy-bakery", "slug": "breads-cakes", "name": "Breads & Cakes", "description": "Sliced bread, multigrain loaves, and packaged cakes"},
    # Grocery → Staples & Grains
    {"category_slug": "staples-grains", "slug": "rice-flour", "name": "Rice & Flour", "description": "Basmati, sona masoori, atta, and besan"},
    {"category_slug": "staples-grains", "slug": "dals-pulses", "name": "Dals & Pulses", "description": "Toor, moong, chana, masoor, and urad dal"},
    {"category_slug": "staples-grains", "slug": "oils-ghee", "name": "Oils & Ghee", "description": "Refined oils, mustard oil, and pure cow ghee"},
    # Electronics → Laptops & Computers
    {"category_slug": "laptops-computers", "slug": "2-in-1-laptops", "name": "2-in-1 Laptops", "description": "Convertible touchscreen laptops"},
    {"category_slug": "laptops-computers", "slug": "gaming-laptops", "name": "Gaming Laptops", "description": "High-performance laptops with discrete GPUs"},
    {"category_slug": "laptops-computers", "slug": "ultrabooks", "name": "Ultrabooks", "description": "Thin, light, premium notebooks"},
    # Electronics → Mobiles & Tablets
    {"category_slug": "mobiles-tablets", "slug": "smartphones", "name": "Smartphones", "description": "Latest flagship and mid-range phones"},
    {"category_slug": "mobiles-tablets", "slug": "tablets", "name": "Tablets", "description": "iPads, Android tablets, and e-readers"},
    {"category_slug": "mobiles-tablets", "slug": "wearables", "name": "Wearables", "description": "Smartwatches and fitness bands"},
    # Electronics → Audio & Accessories
    {"category_slug": "audio-accessories", "slug": "headphones", "name": "Headphones", "description": "Over-ear, in-ear, and noise-cancelling headphones"},
    {"category_slug": "audio-accessories", "slug": "speakers", "name": "Speakers", "description": "Bluetooth and home speakers"},
    {"category_slug": "audio-accessories", "slug": "chargers", "name": "Chargers", "description": "Fast chargers, GaN bricks, and adapters"},
    # Pharmacy → Medicines
    {"category_slug": "medicines", "slug": "pain-relief", "name": "Pain Relief", "description": "Analgesics, sprays, and pain-relief balms"},
    {"category_slug": "medicines", "slug": "cold-flu", "name": "Cold & Flu", "description": "Cough syrups, decongestants, lozenges"},
    {"category_slug": "medicines", "slug": "digestive-care", "name": "Digestive Care", "description": "Antacids, digestives, and gut-health remedies"},
    # Pharmacy → Personal Care
    {"category_slug": "personal-care", "slug": "oral-care", "name": "Oral Care", "description": "Toothpaste, mouthwash, and electric toothbrushes"},
    {"category_slug": "personal-care", "slug": "skin-care", "name": "Skin Care", "description": "Moisturisers, cleansers, and face washes"},
    {"category_slug": "personal-care", "slug": "hair-care", "name": "Hair Care", "description": "Shampoos, conditioners, and hair oils"},
    # Pharmacy → Wellness & Nutrition
    {"category_slug": "wellness-nutrition", "slug": "vitamins", "name": "Vitamins", "description": "Multivitamins and B-complex supplements"},
    {"category_slug": "wellness-nutrition", "slug": "protein-powders", "name": "Protein Powders", "description": "Whey, mass gainers, and malt drinks"},
    {"category_slug": "wellness-nutrition", "slug": "herbal-supplements", "name": "Herbal Supplements", "description": "Ayurvedic tonics, chyawanprash, and herbal tablets"},
]
# Strip helper-only fields (noun/variants/price_range) before merging.
SUBCATEGORIES.extend(
    {k: v for k, v in sub.items() if k in ("category_slug", "slug", "name", "description")}
    for sub in EXTRA_SUBCATEGORIES
)

PRODUCTS: list[dict[str, Any]] = [
    # ----- Grocery → Fruits & Vegetables → Leafy Greens -----
    {"subcategory_slug": "leafy-greens", "slug": "spinach-bunch-palak", "name": "Spinach Bunch (Palak)", "description": "Fresh palak bunch — iron-rich and tender", "base_price": 25},
    {"subcategory_slug": "leafy-greens", "slug": "methi-bunch", "name": "Methi Bunch (Fenugreek)", "description": "Aromatic fenugreek leaves for parathas and sabzi", "base_price": 20},
    {"subcategory_slug": "leafy-greens", "slug": "green-coriander-bunch", "name": "Green Coriander Bunch", "description": "Fresh dhania for garnishing and chutney", "base_price": 15},
    {"subcategory_slug": "leafy-greens", "slug": "mint-bunch-pudina", "name": "Mint Bunch (Pudina)", "description": "Fragrant pudina leaves for chutney and raita", "base_price": 15},
    {"subcategory_slug": "leafy-greens", "slug": "iceberg-lettuce", "name": "Iceberg Lettuce", "description": "Crisp iceberg head — perfect for salads and wraps", "base_price": 60},
    # ----- Grocery → Fruits & Vegetables → Fresh Fruits -----
    {"subcategory_slug": "fresh-fruits", "slug": "bananas-1dozen", "name": "Bananas (1 Dozen)", "description": "Ripe yellow bananas, twelve to a bunch", "base_price": 60},
    {"subcategory_slug": "fresh-fruits", "slug": "alphonso-mangoes-1kg", "name": "Alphonso Mangoes (1kg)", "description": "Premium Ratnagiri Alphonso, sweet and aromatic", "base_price": 450},
    {"subcategory_slug": "fresh-fruits", "slug": "red-apples-1kg", "name": "Red Apples (1kg)", "description": "Crisp Shimla red apples", "base_price": 180},
    {"subcategory_slug": "fresh-fruits", "slug": "pomegranate-1kg", "name": "Pomegranate (1kg)", "description": "Juicy Bhagwa pomegranate with deep red arils", "base_price": 220},
    {"subcategory_slug": "fresh-fruits", "slug": "sweet-lime-mosambi-1kg", "name": "Sweet Lime — Mosambi (1kg)", "description": "Refreshing mosambi for fresh juice", "base_price": 80},
    # ----- Grocery → Fruits & Vegetables → Everyday Vegetables -----
    {"subcategory_slug": "everyday-vegetables", "slug": "fresh-tomatoes", "name": "Fresh Tomatoes", "description": "Firm, red tomatoes — perfect for curries and chutneys", "base_price": 40},
    {"subcategory_slug": "everyday-vegetables", "slug": "onions-pyaaz", "name": "Onions (Pyaaz)", "description": "Medium-sized onions, a kitchen staple", "base_price": 35},
    {"subcategory_slug": "everyday-vegetables", "slug": "potatoes-aloo-1kg", "name": "Potatoes (Aloo) 1kg", "description": "All-purpose potatoes, ideal for sabzi and frying", "base_price": 30},
    {"subcategory_slug": "everyday-vegetables", "slug": "ginger-adrak-250g", "name": "Ginger (Adrak) 250g", "description": "Fresh adrak with strong aroma", "base_price": 25},
    {"subcategory_slug": "everyday-vegetables", "slug": "carrots-gajar-1kg", "name": "Carrots (Gajar) 1kg", "description": "Sweet red carrots — perfect for halwa and salads", "base_price": 50},
    # ----- Grocery → Dairy & Bakery → Milk & Curd -----
    {"subcategory_slug": "milk-curd", "slug": "amul-taza-milk-1l", "name": "Amul Taza Milk (1L)", "description": "Toned milk, pasteurized & homogenized", "base_price": 54},
    {"subcategory_slug": "milk-curd", "slug": "mother-dairy-toned-milk-1l", "name": "Mother Dairy Toned Milk (1L)", "description": "Daily-use toned milk, packed fresh", "base_price": 56},
    {"subcategory_slug": "milk-curd", "slug": "amul-curd-400g", "name": "Amul Masti Dahi (400g)", "description": "Smooth thick curd in a recyclable cup", "base_price": 40},
    {"subcategory_slug": "milk-curd", "slug": "nestle-a-plus-yogurt-400g", "name": "Nestle a+ Greek Yogurt (400g)", "description": "Creamy unsweetened greek-style yogurt", "base_price": 90},
    {"subcategory_slug": "milk-curd", "slug": "amul-buttermilk-1l", "name": "Amul Buttermilk (1L)", "description": "Spiced chaas, ready to serve", "base_price": 45},
    # ----- Grocery → Dairy & Bakery → Cheese & Paneer -----
    {"subcategory_slug": "cheese-paneer", "slug": "amul-paneer-200g", "name": "Amul Paneer (200g)", "description": "Fresh cottage cheese block for sabzi & tikka", "base_price": 90},
    {"subcategory_slug": "cheese-paneer", "slug": "amul-cheese-slices-200g", "name": "Amul Cheese Slices (200g)", "description": "Pack of 10 processed cheese slices", "base_price": 145},
    {"subcategory_slug": "cheese-paneer", "slug": "britannia-cheese-cubes-100g", "name": "Britannia Cheese Cubes (100g)", "description": "Bite-size cheese cubes for snacking", "base_price": 95},
    {"subcategory_slug": "cheese-paneer", "slug": "go-cheese-spread-180g", "name": "Go Cheese Spread (180g)", "description": "Creamy spreadable cheese for sandwiches", "base_price": 130},
    {"subcategory_slug": "cheese-paneer", "slug": "amul-butter-500g", "name": "Amul Butter (500g)", "description": "Salted white butter, classic Indian breakfast staple", "base_price": 270},
    # ----- Grocery → Dairy & Bakery → Breads & Cakes -----
    {"subcategory_slug": "breads-cakes", "slug": "britannia-bread-400g", "name": "Britannia Bread (400g)", "description": "Soft white sandwich bread", "base_price": 45},
    {"subcategory_slug": "breads-cakes", "slug": "harvest-gold-multigrain-bread", "name": "Harvest Gold Multigrain Bread", "description": "Multigrain loaf rich in fiber", "base_price": 65},
    {"subcategory_slug": "breads-cakes", "slug": "modern-brown-bread", "name": "Modern Brown Bread", "description": "Whole-wheat brown bread loaf", "base_price": 50},
    {"subcategory_slug": "breads-cakes", "slug": "britannia-bourbon-cake-200g", "name": "Britannia Bourbon Cake (200g)", "description": "Soft chocolate cream-filled cake", "base_price": 60},
    {"subcategory_slug": "breads-cakes", "slug": "monginis-plum-cake-200g", "name": "Monginis Plum Cake (200g)", "description": "Festive plum cake with raisins and tutti frutti", "base_price": 120},
    # ----- Grocery → Staples & Grains → Rice & Flour -----
    {"subcategory_slug": "rice-flour", "slug": "basmati-rice-5kg", "name": "Basmati Rice (5kg)", "description": "Long grain aged basmati — perfect for biryani", "base_price": 450},
    {"subcategory_slug": "rice-flour", "slug": "sona-masoori-rice-5kg", "name": "Sona Masoori Rice (5kg)", "description": "Light, fluffy everyday rice", "base_price": 380},
    {"subcategory_slug": "rice-flour", "slug": "aashirvaad-atta-5kg", "name": "Aashirvaad Atta (5kg)", "description": "Whole wheat flour for soft rotis", "base_price": 280},
    {"subcategory_slug": "rice-flour", "slug": "aashirvaad-multigrain-atta-5kg", "name": "Aashirvaad Multigrain Atta (5kg)", "description": "Multigrain blend with six grains", "base_price": 360},
    {"subcategory_slug": "rice-flour", "slug": "besan-1kg", "name": "Besan — Gram Flour (1kg)", "description": "Fine gram flour for pakoras and kadhi", "base_price": 110},
    # ----- Grocery → Staples & Grains → Dals & Pulses -----
    {"subcategory_slug": "dals-pulses", "slug": "toor-dal-1kg", "name": "Toor Dal (1kg)", "description": "Premium quality arhar dal for everyday cooking", "base_price": 160},
    {"subcategory_slug": "dals-pulses", "slug": "moong-dal-1kg", "name": "Moong Dal (1kg)", "description": "Yellow split moong, light and easy to digest", "base_price": 140},
    {"subcategory_slug": "dals-pulses", "slug": "masoor-dal-1kg", "name": "Masoor Dal (1kg)", "description": "Pink lentils, fast cooking and protein-rich", "base_price": 130},
    {"subcategory_slug": "dals-pulses", "slug": "chana-dal-1kg", "name": "Chana Dal (1kg)", "description": "Split bengal gram for dal and stuffing", "base_price": 120},
    {"subcategory_slug": "dals-pulses", "slug": "urad-dal-1kg", "name": "Urad Dal (1kg)", "description": "Black gram dal — essential for dosa and dal makhani", "base_price": 150},
    # ----- Grocery → Staples & Grains → Oils & Ghee -----
    {"subcategory_slug": "oils-ghee", "slug": "fortune-sunflower-oil-5l", "name": "Fortune Sunflower Oil (5L)", "description": "Refined sunflower oil for everyday cooking", "base_price": 880},
    {"subcategory_slug": "oils-ghee", "slug": "saffola-gold-oil-5l", "name": "Saffola Gold Oil (5L)", "description": "Blend of rice-bran and corn oil — heart-friendly", "base_price": 1050},
    {"subcategory_slug": "oils-ghee", "slug": "amul-cow-ghee-1l", "name": "Amul Cow Ghee (1L)", "description": "Pure cow ghee, slow-cooked aroma", "base_price": 620},
    {"subcategory_slug": "oils-ghee", "slug": "fortune-mustard-oil-1l", "name": "Fortune Kachi Ghani Mustard Oil (1L)", "description": "Cold-pressed pungent mustard oil", "base_price": 180},
    {"subcategory_slug": "oils-ghee", "slug": "dhara-groundnut-oil-1l", "name": "Dhara Groundnut Oil (1L)", "description": "Refined groundnut oil for deep frying", "base_price": 220},
    # ----- Electronics → Laptops & Computers → 2-in-1 Laptops -----
    {"subcategory_slug": "2-in-1-laptops", "slug": "lenovo-yoga-7i-2in1", "name": "Lenovo Yoga 7i (2-in-1)", "description": "14-inch convertible with Intel Core Ultra 7 and 16GB RAM", "base_price": 99990},
    {"subcategory_slug": "2-in-1-laptops", "slug": "hp-pavilion-x360-14", "name": "HP Pavilion x360 14", "description": "Touchscreen flip laptop with Core i5 13th gen", "base_price": 72990},
    {"subcategory_slug": "2-in-1-laptops", "slug": "dell-inspiron-7430-2in1", "name": "Dell Inspiron 7430 2-in-1", "description": "14-inch Core i7 convertible with active stylus support", "base_price": 89990},
    {"subcategory_slug": "2-in-1-laptops", "slug": "asus-zenbook-flip-14", "name": "ASUS Zenbook Flip 14 OLED", "description": "OLED 360-degree flip laptop, premium build", "base_price": 109990},
    {"subcategory_slug": "2-in-1-laptops", "slug": "microsoft-surface-laptop-studio-2", "name": "Microsoft Surface Laptop Studio 2", "description": "Pull-forward display with RTX 4060 graphics", "base_price": 219990},
    # ----- Electronics → Laptops & Computers → Gaming Laptops -----
    {"subcategory_slug": "gaming-laptops", "slug": "asus-rog-strix-g16", "name": "ASUS ROG Strix G16", "description": "16-inch gaming laptop, Intel i9 + RTX 4070", "base_price": 184990},
    {"subcategory_slug": "gaming-laptops", "slug": "lenovo-legion-pro-5", "name": "Lenovo Legion Pro 5", "description": "Ryzen 7 + RTX 4060 with 165Hz QHD display", "base_price": 159990},
    {"subcategory_slug": "gaming-laptops", "slug": "hp-omen-16", "name": "HP OMEN 16", "description": "16.1-inch QHD 240Hz, Core i7 + RTX 4070", "base_price": 169990},
    {"subcategory_slug": "gaming-laptops", "slug": "msi-katana-15", "name": "MSI Katana 15", "description": "Mid-range gaming, Core i7 + RTX 4060", "base_price": 119990},
    {"subcategory_slug": "gaming-laptops", "slug": "acer-predator-helios-16", "name": "Acer Predator Helios 16", "description": "Mini-LED 16-inch, Core i9 + RTX 4080", "base_price": 219990},
    # ----- Electronics → Laptops & Computers → Ultrabooks -----
    {"subcategory_slug": "ultrabooks", "slug": "macbook-air-m3-13", "name": "MacBook Air M3 (13-inch)", "description": "Apple M3 chip, 8GB RAM, 256GB SSD", "base_price": 114900},
    {"subcategory_slug": "ultrabooks", "slug": "dell-xps-13-plus", "name": "Dell XPS 13 Plus", "description": "Edge-to-edge keyboard, Core i7-1360P, 16GB RAM", "base_price": 159990},
    {"subcategory_slug": "ultrabooks", "slug": "lg-gram-14", "name": "LG Gram 14", "description": "999g featherweight, Intel Core Ultra 7", "base_price": 134990},
    {"subcategory_slug": "ultrabooks", "slug": "asus-zenbook-14-oled", "name": "ASUS Zenbook 14 OLED", "description": "2.8K OLED, Intel Core Ultra 9", "base_price": 124990},
    {"subcategory_slug": "ultrabooks", "slug": "hp-spectre-x360-14", "name": "HP Spectre x360 14", "description": "OLED ultrabook, Core Ultra 7, sleek aluminium chassis", "base_price": 169990},
    # ----- Electronics → Mobiles & Tablets → Smartphones -----
    {"subcategory_slug": "smartphones", "slug": "iphone-15-128gb", "name": "Apple iPhone 15 (128GB)", "description": "A16 Bionic, Dynamic Island, 48MP main camera", "base_price": 79900},
    {"subcategory_slug": "smartphones", "slug": "samsung-galaxy-s24-256gb", "name": "Samsung Galaxy S24 (256GB)", "description": "Snapdragon 8 Gen 3, AI photography suite", "base_price": 84999},
    {"subcategory_slug": "smartphones", "slug": "oneplus-12r-256gb", "name": "OnePlus 12R (256GB)", "description": "Snapdragon 8 Gen 2 with 100W SuperVOOC charging", "base_price": 45999},
    {"subcategory_slug": "smartphones", "slug": "google-pixel-8-128gb", "name": "Google Pixel 8 (128GB)", "description": "Tensor G3, 7 years of OS updates", "base_price": 75999},
    {"subcategory_slug": "smartphones", "slug": "xiaomi-14-pro-256gb", "name": "Xiaomi 14 Pro (256GB)", "description": "Leica camera system, Snapdragon 8 Gen 3", "base_price": 89999},
    # ----- Electronics → Mobiles & Tablets → Tablets -----
    {"subcategory_slug": "tablets", "slug": "ipad-air-m2-128gb", "name": "Apple iPad Air M2 (128GB)", "description": "11-inch Liquid Retina, Apple M2 chip", "base_price": 59900},
    {"subcategory_slug": "tablets", "slug": "samsung-galaxy-tab-s9-128gb", "name": "Samsung Galaxy Tab S9 (128GB)", "description": "11-inch Dynamic AMOLED 2X, S Pen included", "base_price": 72999},
    {"subcategory_slug": "tablets", "slug": "xiaomi-pad-6-128gb", "name": "Xiaomi Pad 6 (128GB)", "description": "11-inch 2.8K 144Hz, Snapdragon 870", "base_price": 28999},
    {"subcategory_slug": "tablets", "slug": "oneplus-pad-128gb", "name": "OnePlus Pad (128GB)", "description": "11.61-inch 2.8K display, Dimensity 9000", "base_price": 37999},
    {"subcategory_slug": "tablets", "slug": "lenovo-tab-p12-128gb", "name": "Lenovo Tab P12 (128GB)", "description": "12.7-inch 3K display, productivity tablet", "base_price": 32999},
    # ----- Electronics → Mobiles & Tablets → Wearables -----
    {"subcategory_slug": "wearables", "slug": "apple-watch-series-9", "name": "Apple Watch Series 9 (45mm GPS)", "description": "S9 SiP, double-tap gesture, brightest display yet", "base_price": 45900},
    {"subcategory_slug": "wearables", "slug": "samsung-galaxy-watch-6-44mm", "name": "Samsung Galaxy Watch 6 (44mm)", "description": "Wear OS, body composition tracking", "base_price": 32999},
    {"subcategory_slug": "wearables", "slug": "noise-colorfit-pro-5", "name": "Noise ColorFit Pro 5", "description": "1.85-inch AMOLED, BT calling, 7-day battery", "base_price": 3499},
    {"subcategory_slug": "wearables", "slug": "boat-storm-pro", "name": "boAt Storm Pro Smartwatch", "description": "1.39-inch AMOLED with always-on display", "base_price": 2499},
    {"subcategory_slug": "wearables", "slug": "fitbit-versa-4", "name": "Fitbit Versa 4", "description": "Built-in GPS, 6+ days battery, daily readiness score", "base_price": 22999},
    # ----- Electronics → Audio & Accessories → Headphones -----
    {"subcategory_slug": "headphones", "slug": "sony-wh-1000xm5", "name": "Sony WH-1000XM5", "description": "Industry-leading ANC, 30-hour battery", "base_price": 29990},
    {"subcategory_slug": "headphones", "slug": "bose-quietcomfort-45", "name": "Bose QuietComfort 45", "description": "Plush ANC over-ears with 24-hour battery", "base_price": 26900},
    {"subcategory_slug": "headphones", "slug": "apple-airpods-pro-2", "name": "Apple AirPods Pro (2nd gen, USB-C)", "description": "H2 chip, Adaptive Audio, Personalized Spatial Audio", "base_price": 24900},
    {"subcategory_slug": "headphones", "slug": "jbl-tune-770nc", "name": "JBL Tune 770NC", "description": "Adaptive ANC over-ear, 70-hour playback", "base_price": 8499},
    {"subcategory_slug": "headphones", "slug": "sennheiser-momentum-4", "name": "Sennheiser Momentum 4", "description": "Audiophile sound, 60-hour battery, premium ANC", "base_price": 27990},
    # ----- Electronics → Audio & Accessories → Speakers -----
    {"subcategory_slug": "speakers", "slug": "jbl-flip-6", "name": "JBL Flip 6", "description": "Portable Bluetooth speaker, IP67 rated", "base_price": 9999},
    {"subcategory_slug": "speakers", "slug": "sony-srs-xb43", "name": "Sony SRS-XB43", "description": "Extra Bass party speaker with mic input", "base_price": 19990},
    {"subcategory_slug": "speakers", "slug": "bose-soundlink-mini-2", "name": "Bose SoundLink Mini II Special Edition", "description": "Compact metal-bodied speaker, 12-hour battery", "base_price": 17900},
    {"subcategory_slug": "speakers", "slug": "marshall-acton-iii", "name": "Marshall Acton III", "description": "Iconic vintage design home Bluetooth speaker", "base_price": 27999},
    {"subcategory_slug": "speakers", "slug": "boat-stone-1500", "name": "boAt Stone 1500", "description": "30W loud party speaker with RGB lights", "base_price": 4999},
    # ----- Electronics → Audio & Accessories → Chargers -----
    {"subcategory_slug": "chargers", "slug": "anker-65w-gan-charger", "name": "Anker 65W GaN Prime Charger", "description": "Compact 3-port GaN brick for laptop and phone", "base_price": 4999},
    {"subcategory_slug": "chargers", "slug": "belkin-magsafe-3in1", "name": "Belkin BoostCharge Pro 3-in-1 MagSafe", "description": "Wirelessly charges iPhone, Watch, AirPods", "base_price": 13999},
    {"subcategory_slug": "chargers", "slug": "mi-50w-sonicfast-charger", "name": "Mi 50W SonicFast Charger", "description": "USB-C PD with 50W fast charge", "base_price": 1499},
    {"subcategory_slug": "chargers", "slug": "apple-20w-usbc-adapter", "name": "Apple 20W USB-C Power Adapter", "description": "Original Apple 20W brick for iPhones and iPads", "base_price": 1900},
    {"subcategory_slug": "chargers", "slug": "realme-supervooc-100w", "name": "Realme SuperVOOC 100W Charger", "description": "100W Type-A charger with Type-C cable", "base_price": 2299},
    # ----- Pharmacy → Medicines → Pain Relief -----
    {"subcategory_slug": "pain-relief", "slug": "crocin-advance-500mg-15s", "name": "Crocin Advance 500mg (Strip of 15)", "description": "Paracetamol for fever and mild pain", "base_price": 35},
    {"subcategory_slug": "pain-relief", "slug": "combiflam-tablet-20s", "name": "Combiflam Tablet (Strip of 20)", "description": "Ibuprofen + paracetamol for pain and inflammation", "base_price": 60},
    {"subcategory_slug": "pain-relief", "slug": "volini-pain-relief-spray-55g", "name": "Volini Pain Relief Spray (55g)", "description": "Spray for muscle and joint pain", "base_price": 240},
    {"subcategory_slug": "pain-relief", "slug": "moov-rapid-spray-35g", "name": "Moov Rapid Pain Relief Spray (35g)", "description": "Quick-action diclofenac spray", "base_price": 195},
    {"subcategory_slug": "pain-relief", "slug": "saridon-tablet-10s", "name": "Saridon Tablet (Strip of 10)", "description": "Trusted headache relief tablet", "base_price": 30},
    # ----- Pharmacy → Medicines → Cold & Flu -----
    {"subcategory_slug": "cold-flu", "slug": "vicks-vaporub-50g", "name": "Vicks VapoRub (50g)", "description": "Topical decongestant for cold and cough relief", "base_price": 165},
    {"subcategory_slug": "cold-flu", "slug": "d-cold-total-tablet-10s", "name": "D'Cold Total Tablet (Strip of 10)", "description": "Multi-symptom cold and flu relief", "base_price": 55},
    {"subcategory_slug": "cold-flu", "slug": "benadryl-cough-syrup-100ml", "name": "Benadryl Cough Syrup (100ml)", "description": "Diphenhydramine syrup for productive cough", "base_price": 130},
    {"subcategory_slug": "cold-flu", "slug": "otrivin-nasal-spray-10ml", "name": "Otrivin Adult Nasal Spray (10ml)", "description": "Decongestant nasal spray, fast acting", "base_price": 110},
    {"subcategory_slug": "cold-flu", "slug": "strepsils-honey-lemon-8s", "name": "Strepsils Honey & Lemon (8 Lozenges)", "description": "Soothing throat lozenges", "base_price": 45},
    # ----- Pharmacy → Medicines → Digestive Care -----
    {"subcategory_slug": "digestive-care", "slug": "eno-fruit-salt-100g", "name": "Eno Regular Fruit Salt (100g)", "description": "Antacid powder, instant acidity relief", "base_price": 110},
    {"subcategory_slug": "digestive-care", "slug": "gelusil-mps-syrup-200ml", "name": "Gelusil MPS Syrup (200ml)", "description": "Mint-flavoured antacid syrup", "base_price": 145},
    {"subcategory_slug": "digestive-care", "slug": "digene-mint-tablet-20s", "name": "Digene Mint Tablet (Strip of 20)", "description": "Chewable antacid tablets", "base_price": 75},
    {"subcategory_slug": "digestive-care", "slug": "pudin-hara-pearls-10s", "name": "Pudin Hara Pearls (Strip of 10)", "description": "Mint-oil capsules for indigestion", "base_price": 30},
    {"subcategory_slug": "digestive-care", "slug": "dabur-hingoli-tablet-40s", "name": "Dabur Hingoli Tablet (Pack of 40)", "description": "Ayurvedic tablet for gas and bloating", "base_price": 60},
    # ----- Pharmacy → Personal Care → Oral Care -----
    {"subcategory_slug": "oral-care", "slug": "colgate-strong-teeth-200g", "name": "Colgate Strong Teeth (200g)", "description": "Calcium-boost toothpaste", "base_price": 110},
    {"subcategory_slug": "oral-care", "slug": "sensodyne-fresh-mint-150g", "name": "Sensodyne Fresh Mint (150g)", "description": "Daily care for sensitive teeth", "base_price": 175},
    {"subcategory_slug": "oral-care", "slug": "pepsodent-germicheck-200g", "name": "Pepsodent Germi-Check (200g)", "description": "12-hour germ protection toothpaste", "base_price": 95},
    {"subcategory_slug": "oral-care", "slug": "listerine-coolmint-500ml", "name": "Listerine Cool Mint Mouthwash (500ml)", "description": "Antibacterial daily mouthwash", "base_price": 230},
    {"subcategory_slug": "oral-care", "slug": "oral-b-vitality-electric", "name": "Oral-B Vitality Electric Toothbrush", "description": "Rechargeable electric brush with timer", "base_price": 1899},
    # ----- Pharmacy → Personal Care → Skin Care -----
    {"subcategory_slug": "skin-care", "slug": "nivea-soft-cream-200ml", "name": "Nivea Soft Light Moisturiser (200ml)", "description": "Light moisturiser with vitamin E", "base_price": 295},
    {"subcategory_slug": "skin-care", "slug": "ponds-white-beauty-100g", "name": "Pond's White Beauty Cream (100g)", "description": "Daily fairness cream with niacinamide", "base_price": 220},
    {"subcategory_slug": "skin-care", "slug": "himalaya-neem-face-wash-150ml", "name": "Himalaya Purifying Neem Face Wash (150ml)", "description": "Anti-acne neem and turmeric face wash", "base_price": 170},
    {"subcategory_slug": "skin-care", "slug": "cetaphil-gentle-cleanser-250ml", "name": "Cetaphil Gentle Skin Cleanser (250ml)", "description": "Soap-free cleanser for sensitive skin", "base_price": 525},
    {"subcategory_slug": "skin-care", "slug": "biotique-bio-honey-gel-150ml", "name": "Biotique Bio Honey Gel (150ml)", "description": "Honey foaming face wash", "base_price": 205},
    # ----- Pharmacy → Personal Care → Hair Care -----
    {"subcategory_slug": "hair-care", "slug": "dove-intense-repair-shampoo-650ml", "name": "Dove Intense Repair Shampoo (650ml)", "description": "Repair shampoo for damaged hair", "base_price": 555},
    {"subcategory_slug": "hair-care", "slug": "pantene-pro-v-shampoo-650ml", "name": "Pantene Pro-V Shampoo (650ml)", "description": "Hair fall control with Pro-V formula", "base_price": 545},
    {"subcategory_slug": "hair-care", "slug": "parachute-coconut-oil-500ml", "name": "Parachute Pure Coconut Oil (500ml)", "description": "100% pure coconut hair oil", "base_price": 240},
    {"subcategory_slug": "hair-care", "slug": "tresemme-keratin-smooth-580ml", "name": "TRESemme Keratin Smooth Shampoo (580ml)", "description": "Keratin-infused smoothening shampoo", "base_price": 525},
    {"subcategory_slug": "hair-care", "slug": "mamaearth-onion-shampoo-400ml", "name": "Mamaearth Onion Hair Shampoo (400ml)", "description": "Onion + plant keratin for hair fall control", "base_price": 449},
    # ----- Pharmacy → Wellness & Nutrition → Vitamins -----
    {"subcategory_slug": "vitamins", "slug": "revital-h-multivitamin-30s", "name": "Revital H Multivitamin (30 Capsules)", "description": "Daily multivitamin with ginseng", "base_price": 295},
    {"subcategory_slug": "vitamins", "slug": "supradyn-daily-multivitamin-15s", "name": "Supradyn Daily Multivitamin (Strip of 15)", "description": "Once-a-day vitamin and mineral tablet", "base_price": 95},
    {"subcategory_slug": "vitamins", "slug": "becosules-capsules-20s", "name": "Becosules Capsules (Strip of 20)", "description": "Vitamin B-complex with vitamin C", "base_price": 65},
    {"subcategory_slug": "vitamins", "slug": "neurobion-forte-tablet-30s", "name": "Neurobion Forte Tablet (Strip of 30)", "description": "Vitamin B-complex tablet for nerve health", "base_price": 50},
    {"subcategory_slug": "vitamins", "slug": "centrum-women-multivitamin-30s", "name": "Centrum Women Multivitamin (30 Tablets)", "description": "Multivitamin formulated for women", "base_price": 540},
    # ----- Pharmacy → Wellness & Nutrition → Protein Powders -----
    {"subcategory_slug": "protein-powders", "slug": "optimum-nutrition-whey-1kg", "name": "Optimum Nutrition Gold Standard Whey (1kg)", "description": "24g whey protein per scoop", "base_price": 4499},
    {"subcategory_slug": "protein-powders", "slug": "muscleblaze-biozyme-2kg", "name": "MuscleBlaze Biozyme Performance Whey (2kg)", "description": "Enhanced absorption whey, 25g protein", "base_price": 5499},
    {"subcategory_slug": "protein-powders", "slug": "gnc-pro-performance-whey-1kg", "name": "GNC Pro Performance Whey (1kg)", "description": "24g whey protein with BCAAs", "base_price": 3299},
    {"subcategory_slug": "protein-powders", "slug": "myprotein-impact-whey-1kg", "name": "Myprotein Impact Whey (1kg)", "description": "21g protein per serving, multiple flavours", "base_price": 2799},
    {"subcategory_slug": "protein-powders", "slug": "horlicks-classic-malt-1kg", "name": "Horlicks Classic Malt (1kg)", "description": "Malt-based health drink, family favourite", "base_price": 480},
    # ----- Pharmacy → Wellness & Nutrition → Herbal Supplements -----
    {"subcategory_slug": "herbal-supplements", "slug": "dabur-chyawanprash-1kg", "name": "Dabur Chyawanprash (1kg)", "description": "Classic Ayurvedic immunity-booster", "base_price": 425},
    {"subcategory_slug": "herbal-supplements", "slug": "patanjali-ashwagandha-60s", "name": "Patanjali Ashwagandha Tablets (Pack of 60)", "description": "Ashwagandha root extract for vitality", "base_price": 80},
    {"subcategory_slug": "herbal-supplements", "slug": "himalaya-tulsi-tablets-60s", "name": "Himalaya Tulsi Tablets (60 Tablets)", "description": "Holy basil tablets for daily wellness", "base_price": 145},
    {"subcategory_slug": "herbal-supplements", "slug": "zandu-pancharishta-450ml", "name": "Zandu Pancharishta (450ml)", "description": "Ayurvedic digestive tonic", "base_price": 195},
    {"subcategory_slug": "herbal-supplements", "slug": "baidyanath-shilajit-20g", "name": "Baidyanath Shilajit Gold (20g)", "description": "Premium pure shilajit resin", "base_price": 1299},
]

# Assign placeholder images from CATEGORY_IMAGE_POOLS to every anchor product.
# Round-robin by index-within-subcategory to evenly distribute the 3 URLs.
# Must run before PRODUCTS.extend(EXTRA_PRODUCTS) so we touch anchor entries
# only (extras already carry their URLs from _generate_extra_products).
_SUBCAT_TO_CATEGORY: dict[str, str] = {sub["slug"]: sub["category_slug"] for sub in SUBCATEGORIES}
_anchor_sub_counter: dict[str, int] = defaultdict(int)
for _product in PRODUCTS:
    _sub_slug = _product["subcategory_slug"]
    _cat_slug = _SUBCAT_TO_CATEGORY[_sub_slug]
    _product["image_url"] = _image_for(_cat_slug, _anchor_sub_counter[_sub_slug])
    _anchor_sub_counter[_sub_slug] += 1

del _SUBCAT_TO_CATEGORY, _anchor_sub_counter, _product, _sub_slug, _cat_slug

PRODUCTS.extend(EXTRA_PRODUCTS)

# All 9 stores anchored in Mumbai with real addresses + radii baked at
# authoring time via `scripts/bake_mumbai_seed.py`. Existing names preserved
# (inventory rows in INVENTORIES key by list position). Radii deliberately
# vary so a single customer address sees a serviceable / not-serviceable mix.
STORES: list[dict[str, Any]] = [
    {
        "name": "Sharma General Store",
        "seller_idx": 1,
        "address_line1": "La Solita",
        "address_line2": "Bandra West",
        "landmark": None,
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400050",
        "country": "India",
        "latitude": 19.0601047,
        "longitude": 72.8309154,
        "place_id": "ChIJdR8zBxXJ5zsR64Phy3jGYhg",
        "location_source": "pin",
        "delivery_radius_km": 5.0,
        "pin_confirmed": True,
    },
    {
        "name": "Krishna Supermart",
        "seller_idx": 2,
        "address_line1": "Laxmi Industrial Estate",
        "address_line2": "Andheri West",
        "landmark": None,
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400053",
        "country": "India",
        "latitude": 19.1351148,
        "longitude": 72.8289904,
        "place_id": "ChIJcUHMQwO25zsRhpNwGgnYIa8",
        "location_source": "pin",
        "delivery_radius_km": 3.0,
        "pin_confirmed": True,
    },
    {
        "name": "Balaji Fresh Market",
        "seller_idx": 3,
        "address_line1": "93",
        "address_line2": "Colaba",
        "landmark": None,
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400005",
        "country": "India",
        "latitude": 18.9099905,
        "longitude": 72.81500129999999,
        "place_id": "ChIJNx5VMY7R5zsR2qpDZIBh9Z8",
        "location_source": "pin",
        "delivery_radius_km": 2.0,
        "pin_confirmed": True,
    },
    {
        "name": "Aditya Tech Hub",
        "seller_idx": 4,
        "address_line1": "Unit No.101-B",
        "address_line2": "Powai (Hiranandani)",
        "landmark": None,
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400076",
        "country": "India",
        "latitude": 19.1170694,
        "longitude": 72.90998309999999,
        "place_id": "ChIJgzb6G03H5zsR2uTl3Lt7uB4",
        "location_source": "pin",
        "delivery_radius_km": 8.0,
        "pin_confirmed": True,
    },
    {
        "name": "Mehta Digital World",
        "seller_idx": 5,
        "address_line1": "1186/202",
        "address_line2": "Worli (Sea Face)",
        "landmark": None,
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400018",
        "country": "India",
        "latitude": 19.0186703,
        "longitude": 72.8161872,
        "place_id": "ChIJ02MiK7vO5zsRp-LFI3hfzXo",
        "location_source": "pin",
        "delivery_radius_km": 5.0,
        "pin_confirmed": True,
    },
    {
        "name": "Iyer Electronics Bazaar",
        "seller_idx": 6,
        "address_line1": "1",
        "address_line2": "Juhu (Tara Rd)",
        "landmark": None,
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400049",
        "country": "India",
        "latitude": 19.0988292,
        "longitude": 72.82631640000001,
        "place_id": "ChIJOw1xwJXJ5zsRbjgfRbESNnQ",
        "location_source": "pin",
        "delivery_radius_km": 1.0,
        "pin_confirmed": True,
    },
    {
        "name": "Wellness First Pharmacy",
        "seller_idx": 7,
        "address_line1": "Dadar",
        "address_line2": "Dadar West (Kabutar Khana)",
        "landmark": None,
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400014",
        "country": "India",
        "latitude": 19.0191157,
        "longitude": 72.8439253,
        "place_id": "ChIJCwutcdzO5zsR_OaUwR9amHQ",
        "location_source": "pin",
        "delivery_radius_km": 15.0,
        "pin_confirmed": True,
    },
    {
        "name": "Reddy MediMart",
        "seller_idx": 8,
        "address_line1": "8",
        "address_line2": "Lower Parel (Kamala Mills)",
        "landmark": None,
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400013",
        "country": "India",
        "latitude": 18.997986,
        "longitude": 72.828964,
        "place_id": "ChIJo-COxPLO5zsRC3u5jYRig7E",
        "location_source": "pin",
        "delivery_radius_km": 4.0,
        "pin_confirmed": True,
    },
    {
        "name": "Bhatt Care Pharmacy",
        "seller_idx": 9,
        "address_line1": "92",
        "address_line2": "Goregaon East (Aarey Rd)",
        "landmark": None,
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400063",
        "country": "India",
        "latitude": 19.1650473,
        "longitude": 72.8509831,
        "place_id": "ChIJL8Wjz1K25zsRtDVS61waA-c",
        "location_source": "pin",
        "delivery_radius_km": 3.0,
        "pin_confirmed": True,
    },
]
STORES.extend(EXTRA_STORES)


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
    "place_id",
    "location_source",
)


def _coerce_location_source(raw: Any) -> LocationSource | None:
    """Accept either a string (`'pin'`) or a `LocationSource` enum and
    return the enum (or None). Lets seed data stay as JSON-friendly strings."""
    if raw is None:
        return None
    if isinstance(raw, LocationSource):
        return raw
    return LocationSource(raw)


def _build_address_kwargs(data: Mapping[str, Any]) -> dict[str, Any]:
    """Project a seed dict to Address column kwargs + auto-derive DIGIPIN.

    Mirrors the production `address_from_payload` helper: any seed entry with
    both lat and lng inside the India bbox gets a DIGIPIN. Out-of-bbox values
    silently produce None (the address still saves)."""
    out: dict[str, Any] = {}
    for key in _ADDRESS_KEYS:
        if key not in data:
            continue
        value = data[key]
        if key == "location_source":
            value = _coerce_location_source(value)
        out[key] = value
    lat, lng = out.get("latitude"), out.get("longitude")
    if lat is not None and lng is not None:
        try:
            out["digipin"] = digipin_encode(lat, lng)
        except ValueError:
            out["digipin"] = None
    return out

_STORES_BY_NAME = {store["name"]: store for store in STORES}
STORE_ITEMS = [
    {
        **store,
        "seller_email": TEST_USERS[store["seller_idx"]]["email"],
    }
    for store in STORES
]

# Inventory: (store_idx, product_slug, price, stock).
# Store indices into STORES list (all in Mumbai post-seed-revamp):
#   0 Sharma General Store    (Bandra West,  5 km radius, grocery)
#   1 Krishna Supermart       (Andheri West, 3 km radius, grocery)
#   2 Balaji Fresh Market     (Colaba,       2 km radius, grocery)
#   3 Aditya Tech Hub         (Powai,        8 km radius, electronics)
#   4 Mehta Digital World     (Worli,        5 km radius, electronics)
#   5 Iyer Electronics Bazaar (Juhu,         1 km radius, electronics)
#   6 Wellness First Pharmacy (Dadar West,  15 km radius, pharmacy)
#   7 Reddy MediMart          (Lower Parel,  4 km radius, pharmacy)
#   8 Bhatt Care Pharmacy     (Goregaon E,   3 km radius, pharmacy)
INVENTORIES: list[tuple[int, str, float, int]] = [
    # Sharma General Store (Gurugram) — broad selection
    (0, "spinach-bunch-palak", 28, 40),
    (0, "green-coriander-bunch", 18, 30),
    (0, "methi-bunch", 22, 25),
    (0, "bananas-1dozen", 65, 35),
    (0, "red-apples-1kg", 190, 25),
    (0, "pomegranate-1kg", 230, 20),
    (0, "fresh-tomatoes", 42, 50),
    (0, "onions-pyaaz", 38, 60),
    (0, "potatoes-aloo-1kg", 32, 70),
    (0, "ginger-adrak-250g", 28, 30),
    (0, "amul-taza-milk-1l", 56, 20),
    (0, "amul-paneer-200g", 95, 15),
    (0, "britannia-bread-400g", 48, 18),
    (0, "toor-dal-1kg", 165, 25),
    (0, "basmati-rice-5kg", 460, 10),
    (0, "aashirvaad-atta-5kg", 285, 12),
    (0, "fortune-sunflower-oil-5l", 895, 8),
    (0, "amul-cow-ghee-1l", 640, 10),
    # Krishna Supermart (Mumbai) — premium-leaning
    (1, "alphonso-mangoes-1kg", 460, 20),
    (1, "red-apples-1kg", 195, 22),
    (1, "pomegranate-1kg", 235, 18),
    (1, "sweet-lime-mosambi-1kg", 85, 30),
    (1, "fresh-tomatoes", 45, 40),
    (1, "onions-pyaaz", 40, 50),
    (1, "potatoes-aloo-1kg", 34, 55),
    (1, "amul-taza-milk-1l", 54, 35),
    (1, "mother-dairy-toned-milk-1l", 58, 30),
    (1, "amul-paneer-200g", 92, 20),
    (1, "amul-cheese-slices-200g", 150, 15),
    (1, "britannia-bread-400g", 46, 18),
    (1, "harvest-gold-multigrain-bread", 70, 12),
    (1, "basmati-rice-5kg", 455, 12),
    (1, "sona-masoori-rice-5kg", 385, 14),
    (1, "saffola-gold-oil-5l", 1075, 6),
    # Balaji Fresh Market (Chennai) — fresh focus
    (2, "spinach-bunch-palak", 25, 50),
    (2, "methi-bunch", 20, 40),
    (2, "mint-bunch-pudina", 16, 35),
    (2, "bananas-1dozen", 60, 60),
    (2, "alphonso-mangoes-1kg", 440, 15),
    (2, "sweet-lime-mosambi-1kg", 78, 45),
    (2, "fresh-tomatoes", 38, 80),
    (2, "onions-pyaaz", 35, 70),
    (2, "potatoes-aloo-1kg", 30, 65),
    (2, "ginger-adrak-250g", 25, 40),
    (2, "carrots-gajar-1kg", 52, 30),
    (2, "toor-dal-1kg", 158, 18),
    (2, "moong-dal-1kg", 138, 16),
    # Aditya Tech Hub (Bengaluru) — premium tech focus
    (3, "lenovo-yoga-7i-2in1", 99990, 6),
    (3, "asus-zenbook-flip-14", 109990, 4),
    (3, "microsoft-surface-laptop-studio-2", 219990, 2),
    (3, "asus-rog-strix-g16", 184990, 5),
    (3, "lenovo-legion-pro-5", 159990, 6),
    (3, "hp-omen-16", 169990, 4),
    (3, "acer-predator-helios-16", 219990, 3),
    (3, "macbook-air-m3-13", 114900, 8),
    (3, "dell-xps-13-plus", 159990, 5),
    (3, "asus-zenbook-14-oled", 124990, 6),
    (3, "iphone-15-128gb", 79900, 12),
    (3, "samsung-galaxy-s24-256gb", 84999, 10),
    (3, "oneplus-12r-256gb", 45999, 15),
    (3, "google-pixel-8-128gb", 75999, 8),
    (3, "ipad-air-m2-128gb", 59900, 7),
    (3, "samsung-galaxy-tab-s9-128gb", 72999, 5),
    (3, "apple-watch-series-9", 45900, 9),
    (3, "samsung-galaxy-watch-6-44mm", 32999, 8),
    (3, "sony-wh-1000xm5", 29990, 14),
    (3, "apple-airpods-pro-2", 24900, 18),
    (3, "bose-quietcomfort-45", 26900, 10),
    (3, "jbl-flip-6", 9999, 22),
    (3, "bose-soundlink-mini-2", 17900, 8),
    (3, "anker-65w-gan-charger", 4999, 30),
    (3, "apple-20w-usbc-adapter", 1900, 40),
    # Mehta Digital World (Pune) — mainstream + value
    (4, "hp-pavilion-x360-14", 72990, 8),
    (4, "dell-inspiron-7430-2in1", 89990, 6),
    (4, "msi-katana-15", 119990, 7),
    (4, "lenovo-legion-pro-5", 161990, 4),
    (4, "hp-omen-16", 171990, 5),
    (4, "macbook-air-m3-13", 115900, 6),
    (4, "lg-gram-14", 134990, 4),
    (4, "hp-spectre-x360-14", 169990, 3),
    (4, "iphone-15-128gb", 79900, 0),
    (4, "oneplus-12r-256gb", 46499, 12),
    (4, "xiaomi-14-pro-256gb", 89999, 6),
    (4, "xiaomi-pad-6-128gb", 28999, 10),
    (4, "oneplus-pad-128gb", 37999, 8),
    (4, "lenovo-tab-p12-128gb", 32999, 7),
    (4, "noise-colorfit-pro-5", 3499, 35),
    (4, "boat-storm-pro", 2499, 40),
    (4, "fitbit-versa-4", 22999, 9),
    (4, "jbl-tune-770nc", 8499, 20),
    (4, "sony-wh-1000xm5", 30490, 8),
    (4, "sennheiser-momentum-4", 27990, 5),
    (4, "jbl-flip-6", 10199, 18),
    (4, "sony-srs-xb43", 19990, 10),
    (4, "boat-stone-1500", 4999, 25),
    (4, "mi-50w-sonicfast-charger", 1499, 30),
    (4, "realme-supervooc-100w", 2299, 25),
    (4, "anker-65w-gan-charger", 5099, 22),
    # Iyer Electronics Bazaar (Hyderabad) — broad mid-range
    (5, "lenovo-yoga-7i-2in1", 101990, 4),
    (5, "dell-inspiron-7430-2in1", 91490, 5),
    (5, "asus-rog-strix-g16", 184990, 0),
    (5, "msi-katana-15", 121490, 6),
    (5, "dell-xps-13-plus", 161990, 4),
    (5, "asus-zenbook-14-oled", 126490, 5),
    (5, "lg-gram-14", 136490, 3),
    (5, "hp-spectre-x360-14", 171490, 4),
    (5, "samsung-galaxy-s24-256gb", 86499, 8),
    (5, "google-pixel-8-128gb", 76999, 6),
    (5, "xiaomi-14-pro-256gb", 90999, 5),
    (5, "ipad-air-m2-128gb", 60900, 6),
    (5, "samsung-galaxy-tab-s9-128gb", 73999, 4),
    (5, "xiaomi-pad-6-128gb", 29499, 9),
    (5, "apple-watch-series-9", 46500, 7),
    (5, "samsung-galaxy-watch-6-44mm", 33499, 6),
    (5, "noise-colorfit-pro-5", 3599, 30),
    (5, "boat-storm-pro", 2599, 35),
    (5, "bose-quietcomfort-45", 27400, 8),
    (5, "jbl-tune-770nc", 8699, 16),
    (5, "apple-airpods-pro-2", 25400, 14),
    (5, "sony-srs-xb43", 20290, 9),
    (5, "marshall-acton-iii", 27999, 4),
    (5, "boat-stone-1500", 5099, 22),
    (5, "belkin-magsafe-3in1", 13999, 7),
    (5, "mi-50w-sonicfast-charger", 1499, 28),
    (5, "realme-supervooc-100w", 2299, 24),
    # Wellness First Pharmacy (Delhi) — broad essentials
    (6, "crocin-advance-500mg-15s", 35, 100),
    (6, "combiflam-tablet-20s", 60, 80),
    (6, "volini-pain-relief-spray-55g", 240, 30),
    (6, "saridon-tablet-10s", 30, 90),
    (6, "moov-rapid-spray-35g", 195, 25),
    (6, "vicks-vaporub-50g", 165, 60),
    (6, "d-cold-total-tablet-10s", 55, 70),
    (6, "benadryl-cough-syrup-100ml", 130, 35),
    (6, "otrivin-nasal-spray-10ml", 110, 28),
    (6, "strepsils-honey-lemon-8s", 45, 75),
    (6, "eno-fruit-salt-100g", 110, 50),
    (6, "gelusil-mps-syrup-200ml", 145, 30),
    (6, "digene-mint-tablet-20s", 75, 60),
    (6, "pudin-hara-pearls-10s", 30, 80),
    (6, "colgate-strong-teeth-200g", 110, 65),
    (6, "sensodyne-fresh-mint-150g", 175, 40),
    (6, "listerine-coolmint-500ml", 230, 25),
    (6, "nivea-soft-cream-200ml", 295, 35),
    (6, "ponds-white-beauty-100g", 220, 0),
    (6, "himalaya-neem-face-wash-150ml", 170, 45),
    (6, "dove-intense-repair-shampoo-650ml", 555, 20),
    (6, "parachute-coconut-oil-500ml", 240, 50),
    (6, "revital-h-multivitamin-30s", 295, 30),
    (6, "supradyn-daily-multivitamin-15s", 95, 55),
    (6, "optimum-nutrition-whey-1kg", 4499, 12),
    (6, "horlicks-classic-malt-1kg", 480, 25),
    (6, "dabur-chyawanprash-1kg", 425, 30),
    (6, "patanjali-ashwagandha-60s", 80, 60),
    # Reddy MediMart (Kolkata) — value + ayurvedic focus
    (7, "crocin-advance-500mg-15s", 34, 90),
    (7, "combiflam-tablet-20s", 58, 75),
    (7, "saridon-tablet-10s", 28, 85),
    (7, "moov-rapid-spray-35g", 189, 22),
    (7, "vicks-vaporub-50g", 162, 0),
    (7, "d-cold-total-tablet-10s", 53, 65),
    (7, "strepsils-honey-lemon-8s", 43, 70),
    (7, "eno-fruit-salt-100g", 108, 45),
    (7, "digene-mint-tablet-20s", 73, 55),
    (7, "pudin-hara-pearls-10s", 29, 75),
    (7, "dabur-hingoli-tablet-40s", 58, 40),
    (7, "colgate-strong-teeth-200g", 108, 60),
    (7, "pepsodent-germicheck-200g", 93, 50),
    (7, "oral-b-vitality-electric", 1899, 8),
    (7, "ponds-white-beauty-100g", 218, 30),
    (7, "himalaya-neem-face-wash-150ml", 168, 42),
    (7, "biotique-bio-honey-gel-150ml", 205, 25),
    (7, "pantene-pro-v-shampoo-650ml", 545, 18),
    (7, "parachute-coconut-oil-500ml", 235, 48),
    (7, "mamaearth-onion-shampoo-400ml", 449, 22),
    (7, "supradyn-daily-multivitamin-15s", 93, 50),
    (7, "becosules-capsules-20s", 65, 70),
    (7, "neurobion-forte-tablet-30s", 50, 60),
    (7, "muscleblaze-biozyme-2kg", 5499, 6),
    (7, "gnc-pro-performance-whey-1kg", 3299, 8),
    (7, "horlicks-classic-malt-1kg", 475, 22),
    (7, "dabur-chyawanprash-1kg", 419, 28),
    (7, "patanjali-ashwagandha-60s", 78, 55),
    (7, "himalaya-tulsi-tablets-60s", 145, 35),
    (7, "zandu-pancharishta-450ml", 195, 18),
    # Bhatt Care Pharmacy (Ahmedabad) — premium + niche
    (8, "crocin-advance-500mg-15s", 36, 80),
    (8, "combiflam-tablet-20s", 62, 70),
    (8, "volini-pain-relief-spray-55g", 248, 25),
    (8, "saridon-tablet-10s", 32, 75),
    (8, "vicks-vaporub-50g", 170, 50),
    (8, "benadryl-cough-syrup-100ml", 135, 28),
    (8, "otrivin-nasal-spray-10ml", 115, 22),
    (8, "strepsils-honey-lemon-8s", 48, 60),
    (8, "gelusil-mps-syrup-200ml", 150, 26),
    (8, "digene-mint-tablet-20s", 78, 45),
    (8, "dabur-hingoli-tablet-40s", 62, 35),
    (8, "sensodyne-fresh-mint-150g", 180, 32),
    (8, "listerine-coolmint-500ml", 235, 22),
    (8, "oral-b-vitality-electric", 1949, 7),
    (8, "pepsodent-germicheck-200g", 99, 42),
    (8, "nivea-soft-cream-200ml", 299, 28),
    (8, "cetaphil-gentle-cleanser-250ml", 525, 15),
    (8, "biotique-bio-honey-gel-150ml", 210, 22),
    (8, "dove-intense-repair-shampoo-650ml", 565, 16),
    (8, "tresemme-keratin-smooth-580ml", 525, 14),
    # --- Cross-service stock (multi-service sellers) ---
    # Sharma General Store (grocery + pharmacy) — OTC basics
    (0, "crocin-advance-500mg-15s", 36, 70),
    (0, "combiflam-tablet-20s", 60, 50),
    (0, "vicks-vaporub-50g", 165, 40),
    (0, "saridon-tablet-10s", 30, 80),
    (0, "eno-fruit-salt-100g", 110, 35),
    (0, "digene-mint-tablet-20s", 75, 30),
    (0, "colgate-strong-teeth-200g", 110, 50),
    (0, "parachute-coconut-oil-500ml", 240, 35),
    # Krishna Supermart (grocery + electronics) — small electronics
    (1, "noise-colorfit-pro-5", 3499, 18),
    (1, "boat-storm-pro", 2499, 25),
    (1, "jbl-flip-6", 9999, 12),
    (1, "boat-stone-1500", 4999, 15),
    (1, "mi-50w-sonicfast-charger", 1499, 30),
    (1, "apple-20w-usbc-adapter", 1900, 25),
    # Bhatt Care Pharmacy (pharmacy + grocery) — kitchen essentials
    (8, "amul-taza-milk-1l", 56, 25),
    (8, "amul-paneer-200g", 95, 15),
    (8, "britannia-bread-400g", 48, 20),
    (8, "toor-dal-1kg", 162, 18),
    (8, "aashirvaad-atta-5kg", 290, 14),
    (8, "amul-cow-ghee-1l", 645, 10),
    (8, "fresh-tomatoes", 44, 30),
    (8, "onions-pyaaz", 38, 40),
    (8, "mamaearth-onion-shampoo-400ml", 459, 18),
    (8, "pantene-pro-v-shampoo-650ml", 555, 15),
    (8, "revital-h-multivitamin-30s", 299, 25),
    (8, "becosules-capsules-20s", 67, 60),
    (8, "neurobion-forte-tablet-30s", 52, 55),
    (8, "centrum-women-multivitamin-30s", 540, 18),
    (8, "optimum-nutrition-whey-1kg", 4599, 8),
    (8, "muscleblaze-biozyme-2kg", 5599, 5),
    (8, "myprotein-impact-whey-1kg", 2799, 10),
    (8, "himalaya-tulsi-tablets-60s", 148, 30),
    (8, "zandu-pancharishta-450ml", 199, 16),
    (8, "baidyanath-shilajit-20g", 1299, 6),
]

INVENTORY_ITEMS = [
    {
        "store_name": STORES[store_idx]["name"],
        "product_slug": product_slug,
        "price": price,
        "stock": stock,
    }
    for store_idx, product_slug, price, stock in INVENTORIES
]

STORE_OWNER_PROFILES: list[dict[str, Any]] = [
    {
        "email": "seller@khanabazaar.dev",
        "full_name": "Ravi Sharma",
        "business_name": "Sharma General Store",
        "service_slugs": ["grocery", "pharmacy"],
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
        "service_slugs": ["grocery", "electronics"],
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
        "service_slugs": ["grocery"],
        "phone": "+919811110003",
        "gst_number": "33CCCCC3333C3Z3",
        "fssai_license": "66778899001122",
        "bank_account_number": "00100200300900",
        "bank_ifsc": "SBIN0000003",
        "status": VerificationStatus.Approved,
        "rejection_reason": None,
        **{key: _STORES_BY_NAME["Balaji Fresh Market"][key] for key in _ADDRESS_KEYS},
    },
    {
        "email": "seller4@khanabazaar.dev",
        "full_name": "Aditya Khanna",
        "business_name": "Aditya Tech Hub",
        "service_slugs": ["electronics"],
        "phone": "+919811110004",
        "gst_number": "29DDDDD4444D4Z4",
        "fssai_license": "77889900112233",
        "bank_account_number": "10100200301000",
        "bank_ifsc": "HDFC0000004",
        "status": VerificationStatus.Approved,
        "rejection_reason": None,
        **{key: _STORES_BY_NAME["Aditya Tech Hub"][key] for key in _ADDRESS_KEYS},
    },
    {
        "email": "seller5@khanabazaar.dev",
        "full_name": "Rahul Mehta",
        "business_name": "Mehta Digital World",
        "service_slugs": ["electronics"],
        "phone": "+919811110005",
        "gst_number": "27EEEEE5555E5Z5",
        "fssai_license": "88990011223344",
        "bank_account_number": "20100200301100",
        "bank_ifsc": "ICIC0000005",
        "status": VerificationStatus.Approved,
        "rejection_reason": None,
        **{key: _STORES_BY_NAME["Mehta Digital World"][key] for key in _ADDRESS_KEYS},
    },
    {
        "email": "seller6@khanabazaar.dev",
        "full_name": "Neha Iyer",
        "business_name": "Iyer Electronics Bazaar",
        "service_slugs": ["electronics"],
        "phone": "+919811110006",
        "gst_number": "36FFFFF6666F6Z6",
        "fssai_license": "99001122334455",
        "bank_account_number": "30100200301200",
        "bank_ifsc": "AXIS0000006",
        "status": VerificationStatus.Approved,
        "rejection_reason": None,
        **{key: _STORES_BY_NAME["Iyer Electronics Bazaar"][key] for key in _ADDRESS_KEYS},
    },
    {
        "email": "seller7@khanabazaar.dev",
        "full_name": "Anjali Gupta",
        "business_name": "Wellness First Pharmacy",
        "service_slugs": ["pharmacy"],
        "phone": "+919811110007",
        "gst_number": "07GGGGG7777G7Z7",
        "fssai_license": "10112233445566",
        "bank_account_number": "40100200301300",
        "bank_ifsc": "HDFC0000007",
        "status": VerificationStatus.Approved,
        "rejection_reason": None,
        **{key: _STORES_BY_NAME["Wellness First Pharmacy"][key] for key in _ADDRESS_KEYS},
    },
    {
        "email": "seller8@khanabazaar.dev",
        "full_name": "Suresh Reddy",
        "business_name": "Reddy MediMart",
        "service_slugs": ["pharmacy"],
        "phone": "+919811110008",
        "gst_number": "19HHHHH8888H8Z8",
        "fssai_license": "11223344556678",
        "bank_account_number": "50100200301400",
        "bank_ifsc": "SBIN0000008",
        "status": VerificationStatus.Approved,
        "rejection_reason": None,
        **{key: _STORES_BY_NAME["Reddy MediMart"][key] for key in _ADDRESS_KEYS},
    },
    {
        "email": "seller9@khanabazaar.dev",
        "full_name": "Pooja Bhatt",
        "business_name": "Bhatt Care Pharmacy",
        "service_slugs": ["pharmacy", "grocery"],
        "phone": "+919811110009",
        "gst_number": "24IIIII9999I9Z9",
        "fssai_license": "22334455667789",
        "bank_account_number": "60100200301500",
        "bank_ifsc": "ICIC0000009",
        "status": VerificationStatus.Approved,
        "rejection_reason": None,
        **{key: _STORES_BY_NAME["Bhatt Care Pharmacy"][key] for key in _ADDRESS_KEYS},
    },
]
# Merge extra owners with their matching store's address fields. EXTRA_STORE_OWNER_PROFILES
# carries business_name == store["name"], so the join is by name. _STORES_BY_NAME now spans
# all 90 stores because STORES was extended before this dict was built.
STORE_OWNER_PROFILES.extend(
    {
        **owner,
        **{key: _STORES_BY_NAME[owner["business_name"]][key] for key in _ADDRESS_KEYS},
    }
    for owner in EXTRA_STORE_OWNER_PROFILES
)

# Generate inventory rows for the 81 extra stores. Each store gets 30–50 SKUs
# sampled from its services, with ±20% price jitter and ~8% out-of-stock for
# QA coverage. Anchor stores live at indices 0..8; extras at 9..89.
INVENTORIES.extend(
    generate_extra_inventories(
        all_services=SERVICES,
        all_categories=CATEGORIES,
        all_subcategories=SUBCATEGORIES,
        all_products=PRODUCTS,
        anchor_store_count=9,
    )
)
# Rebuild INVENTORY_ITEMS to reflect the merged INVENTORIES list. (The earlier
# comprehension fired before extension, so we replace it with a fresh build.)
INVENTORY_ITEMS = [
    {
        "store_name": STORES[store_idx]["name"],
        "product_slug": product_slug,
        "price": price,
        "stock": stock,
    }
    for store_idx, product_slug, price, stock in INVENTORIES
]


# ---------------------------------------------------------------------------
# DEMO ORDERS — exercise every Order status and span multiple customers,
# stores, and services. Idempotent: the seeder skips if any Order rows exist.
# Each entry references customer/store/address by stable identifiers (email,
# store name, address label) and lists items as (product_slug, quantity).
# `days_ago` offsets `placed_at` backwards so order history looks lived-in.
# ---------------------------------------------------------------------------
DEMO_ORDERS: list[dict[str, Any]] = [
    {
        "customer_email": "customer@khanabazaar.dev",
        "store_name": "Sharma General Store",
        "service_slug": "grocery",
        "address_label": "Home",
        "status": "delivered",
        "payment_method": "upi",
        "days_ago": 7,
        "items": [
            ("fresh-tomatoes", 2),
            ("amul-taza-milk-1l", 1),
            ("britannia-bread-400g", 1),
        ],
    },
    {
        "customer_email": "customer@khanabazaar.dev",
        "store_name": "Aditya Tech Hub",
        "service_slug": "electronics",
        "address_label": "Office",
        "status": "dispatched",
        "payment_method": "upi",
        "days_ago": 1,
        "items": [
            ("sony-wh-1000xm5", 1),
            ("anker-65w-gan-charger", 1),
        ],
    },
    {
        "customer_email": "customer@khanabazaar.dev",
        "store_name": "Wellness First Pharmacy",
        "service_slug": "pharmacy",
        "address_label": "Home",
        "status": "packed",
        "payment_method": "cash",
        "days_ago": 0,
        "items": [
            ("crocin-advance-500mg-15s", 2),
            ("vicks-vaporub-50g", 1),
        ],
    },
    {
        "customer_email": "customer2@khanabazaar.dev",
        "store_name": "Krishna Supermart",
        "service_slug": "grocery",
        "address_label": "Home",
        "status": "delivered",
        "payment_method": "upi",
        "days_ago": 4,
        "items": [
            ("alphonso-mangoes-1kg", 1),
            ("amul-paneer-200g", 1),
            ("amul-taza-milk-1l", 2),
        ],
    },
    {
        "customer_email": "customer3@khanabazaar.dev",
        "store_name": "Mehta Digital World",
        "service_slug": "electronics",
        "address_label": "Home",
        "status": "pending",
        "payment_method": "upi",
        "days_ago": 0,
        "items": [
            ("boat-storm-pro", 1),
        ],
    },
    {
        "customer_email": "customer4@khanabazaar.dev",
        "store_name": "Balaji Fresh Market",
        "service_slug": "grocery",
        "address_label": "Home",
        "status": "delivered",
        "payment_method": "cash",
        "days_ago": 10,
        "items": [
            ("bananas-1dozen", 1),
            ("fresh-tomatoes", 2),
            ("potatoes-aloo-1kg", 1),
        ],
    },
    {
        "customer_email": "customer5@khanabazaar.dev",
        "store_name": "Reddy MediMart",
        "service_slug": "pharmacy",
        "address_label": "Home",
        "status": "cancelled",
        "payment_method": "upi",
        "days_ago": 6,
        "items": [
            ("crocin-advance-500mg-15s", 1),
        ],
    },
    {
        "customer_email": "customer6@khanabazaar.dev",
        "store_name": "Iyer Electronics Bazaar",
        "service_slug": "electronics",
        "address_label": "Home",
        "status": "dispatched",
        "payment_method": "upi",
        "days_ago": 2,
        "items": [
            ("apple-airpods-pro-2", 1),
        ],
    },
    {
        "customer_email": "customer7@khanabazaar.dev",
        "store_name": "Bhatt Care Pharmacy",
        "service_slug": "pharmacy",
        "address_label": "Home",
        "status": "delivered",
        "payment_method": "cash",
        "days_ago": 14,
        "items": [
            ("sensodyne-fresh-mint-150g", 1),
            ("listerine-coolmint-500ml", 1),
        ],
    },
    {
        "customer_email": "customer8@khanabazaar.dev",
        "store_name": "Sharma General Store",
        "service_slug": "pharmacy",
        "address_label": "Home",
        "status": "packed",
        "payment_method": "upi",
        "days_ago": 0,
        "items": [
            ("colgate-strong-teeth-200g", 1),
            ("eno-fruit-salt-100g", 1),
        ],
    },
    {
        "customer_email": "customer9@khanabazaar.dev",
        "store_name": "Wellness First Pharmacy",
        "service_slug": "pharmacy",
        "address_label": "Home",
        "status": "delivered",
        "payment_method": "upi",
        "days_ago": 5,
        "items": [
            ("patanjali-ashwagandha-60s", 2),
            ("horlicks-classic-malt-1kg", 1),
        ],
    },
    {
        "customer_email": "customer10@khanabazaar.dev",
        "store_name": "Aditya Tech Hub",
        "service_slug": "electronics",
        "address_label": "Home",
        "status": "pending",
        "payment_method": "cash",
        "days_ago": 0,
        "items": [
            ("iphone-15-128gb", 1),
        ],
    },
]


def _compute_expected_counts() -> dict[str, int]:
    """Derive expected counts from the merged module-level data. Keeps the
    EXPECTED_FULL_COUNTS dict honest if extra-data generation ever shifts
    (e.g., new neighborhood entries, different RNG seed)."""
    customer_address_count = sum(len(c.get("addresses", [])) for c in CUSTOMERS)
    # Each store + customer-address + seller-profile (owner) + application carries 1 Address row.
    address_count = (
        len(STORES)
        + customer_address_count
        + len(STORE_OWNER_PROFILES)
        + len(APPLICATIONS)
    )
    # SellerProfileService links: sum of len(service_slugs) across owners + applications.
    seller_service_links = sum(len(p["service_slugs"]) for p in STORE_OWNER_PROFILES) + sum(
        len(a["service_slugs"]) for a in APPLICATIONS
    )
    # Users: TEST_USERS roster (admin + sellers + customers) + APPLICATIONS sellers.
    user_count = len(TEST_USERS) + len(APPLICATIONS)
    return {
        "users": user_count,
        "language": len(LANGUAGES),
        "customerprofile": len(CUSTOMERS),
        "customeraddress": customer_address_count,
        "adminprofile": 1,
        "sellerprofile": len(STORE_OWNER_PROFILES) + len(APPLICATIONS),
        "sellerprofile_service": seller_service_links,
        "address": address_count,
        "service": len(SERVICES),
        "service_translation": len(SERVICES),
        "category": len(CATEGORIES),
        "category_translation": len(CATEGORIES),
        "subcategory": len(SUBCATEGORIES),
        "subcategory_translation": len(SUBCATEGORIES),
        "masterproduct": len(PRODUCTS),
        "masterproduct_translation": len(PRODUCTS),
        "store": len(STORES),
        "storeinventory": len(INVENTORIES),
        "order": len(DEMO_ORDERS),
        "orderitem": sum(len(o["items"]) for o in DEMO_ORDERS),
        "payment": len(DEMO_ORDERS),
        "delivery": len(DEMO_ORDERS),
    }


EXPECTED_FULL_COUNTS = _compute_expected_counts()


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
    """Update existing owner-linked address, or insert a new one. Auto-derives
    DIGIPIN from lat/lng via `_build_address_kwargs` (mirrors the production
    `address_from_payload` helper)."""
    address_fields = _build_address_kwargs(data)
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


async def _upsert_seller_profile_services(
    session: AsyncSession, profile: SellerProfile, service_slugs: list[str]
) -> None:
    assert profile.id is not None
    service_ids: list[int] = []
    for slug in service_slugs:
        result = await session.exec(select(Service).where(Service.slug == slug))
        service = result.first()
        assert service is not None and service.id is not None, (
            f"seed expected service with slug={slug!r}; ensure SERVICES are seeded first"
        )
        service_ids.append(service.id)

    existing_result = await session.exec(
        select(SellerProfileService).where(
            SellerProfileService.seller_profile_id == profile.id
        )
    )
    existing = {row.service_id: row for row in existing_result.all()}
    desired = set(service_ids)

    for service_id in desired - existing.keys():
        session.add(
            SellerProfileService(seller_profile_id=profile.id, service_id=service_id)
        )
    for service_id, row in list(existing.items()):
        if service_id not in desired:
            await session.delete(row)
    await session.flush()


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
        profile.gst_number = data["gst_number"]
        profile.fssai_license = data["fssai_license"]
        profile.bank_account_number = data["bank_account_number"]
        profile.bank_ifsc = data["bank_ifsc"]
        profile.verification_status = data["status"]
        profile.rejection_reason = data["rejection_reason"]
    session.add(profile)
    await session.flush()
    await _upsert_seller_profile_services(session, profile, data["service_slugs"])
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


async def _upsert_customer_addresses(
    session: AsyncSession,
    profile: CustomerProfile,
    addresses: list[dict[str, Any]],
) -> None:
    """Idempotent: skips entries whose `(profile_id, label)` join row already
    exists. Each address gets its own `Address` row plus a `CustomerAddress`
    join row carrying the label + is_default flag."""
    assert profile.id is not None
    existing = await session.exec(
        select(CustomerAddress).where(
            CustomerAddress.customer_profile_id == profile.id
        )
    )
    have_labels = {row.label for row in existing.all()}
    for entry in addresses:
        label = entry.get("label")
        if label in have_labels:
            continue
        address = await _upsert_address(session, None, entry)
        assert address.id is not None
        session.add(CustomerAddress(
            customer_profile_id=profile.id,
            address_id=address.id,
            label=label,
            is_default=bool(entry.get("is_default", False)),
        ))
    await session.flush()


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


async def _upsert_subcategory(
    session: AsyncSession, category_id: int, data: Mapping[str, Any], sort_order: int
) -> Subcategory:
    result = await session.exec(
        select(Subcategory).where(
            Subcategory.category_id == category_id,
            Subcategory.slug == data["slug"],
        )
    )
    sub = result.first()
    if sub is None:
        sub = Subcategory(
            category_id=category_id, slug=data["slug"], sort_order=sort_order
        )
    else:
        sub.sort_order = sort_order
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
                name=data["name"],
                description=data.get("description"),
            )
        )
    else:
        translation.name = data["name"]
        translation.description = data.get("description")
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
            delivery_radius_km=float(data.get("delivery_radius_km", 5.0)),
            pin_confirmed=bool(data.get("pin_confirmed", False)),
        )
    else:
        existing_address = await session.get(Address, store.address_id)
        await _upsert_address(session, existing_address, data)
        store.is_active = True
        if "delivery_radius_km" in data:
            store.delivery_radius_km = float(data["delivery_radius_km"])
        if "pin_confirmed" in data:
            store.pin_confirmed = bool(data["pin_confirmed"])
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


async def _seed_demo_orders(session: AsyncSession) -> None:
    """Build the DEMO_ORDERS roster: Order + OrderItem + Payment + Delivery
    rows, with status-appropriate timestamps and stock decrements. Idempotent
    — skips entirely if any Order rows already exist (the seed wipes nothing,
    so a second call would otherwise duplicate the entire roster)."""
    existing = await session.exec(select(func.count()).select_from(Order))
    if int(existing.one()) > 0:
        return

    now = datetime.now(timezone.utc)

    for spec in DEMO_ORDERS:
        user_result = await session.exec(
            select(User).where(User.email == spec["customer_email"])
        )
        user = user_result.first()
        assert user is not None and user.id is not None, (
            f"demo order references unknown customer {spec['customer_email']!r}"
        )

        profile_result = await session.exec(
            select(CustomerProfile).where(CustomerProfile.user_id == user.id)
        )
        profile = profile_result.first()
        assert profile is not None and profile.id is not None

        address_row = await session.exec(
            select(CustomerAddress, Address)
            .join(Address, Address.id == CustomerAddress.address_id)  # type: ignore[arg-type]
            .where(
                CustomerAddress.customer_profile_id == profile.id,
                CustomerAddress.label == spec["address_label"],
            )
        )
        addr_pair = address_row.first()
        assert addr_pair is not None, (
            f"demo order: customer {spec['customer_email']} has no "
            f"address with label {spec['address_label']!r}"
        )
        _, address = addr_pair
        assert address.id is not None
        address_snapshot = format_address(address_to_payload(address))

        store_result = await session.exec(
            select(Store).where(Store.name == spec["store_name"])
        )
        store = store_result.first()
        assert store is not None and store.id is not None, (
            f"demo order references unknown store {spec['store_name']!r}"
        )

        service_result = await session.exec(
            select(Service).where(Service.slug == spec["service_slug"])
        )
        service = service_result.first()
        assert service is not None and service.id is not None

        service_name_row = await session.exec(
            select(ServiceTranslation.name).where(
                ServiceTranslation.service_id == service.id,
                ServiceTranslation.language_code == "en",
            )
        )
        service_name = service_name_row.first() or service.slug

        placed_at = now - timedelta(days=int(spec["days_ago"]))
        status = OrderStatus(spec["status"])
        payment_method = PaymentMethod(spec["payment_method"])

        order_items: list[tuple[OrderItem, StoreInventory, int]] = []
        subtotal = 0.0
        for product_slug, qty in spec["items"]:
            product_row = await session.exec(
                select(MasterProduct).where(MasterProduct.slug == product_slug)
            )
            product = product_row.first()
            assert product is not None and product.id is not None, (
                f"demo order references unknown product slug {product_slug!r}"
            )

            inv_row = await session.exec(
                select(StoreInventory).where(
                    StoreInventory.store_id == store.id,
                    StoreInventory.product_id == product.id,
                )
            )
            inventory = inv_row.first()
            assert inventory is not None and inventory.id is not None, (
                f"demo order: store {spec['store_name']!r} has no inventory "
                f"row for product {product_slug!r}"
            )

            name_row = await session.exec(
                select(MasterProductTranslation.name).where(
                    MasterProductTranslation.master_product_id == product.id,
                    MasterProductTranslation.language_code == "en",
                )
            )
            product_name = name_row.first() or product.slug

            line_total = float(inventory.price) * qty
            subtotal += line_total
            order_items.append((
                OrderItem(
                    inventory_id=inventory.id,
                    product_name_snapshot=product_name,
                    unit_price_snapshot=float(inventory.price),
                    quantity=qty,
                    line_total=line_total,
                ),
                inventory,
                qty,
            ))

        order = Order(
            customer_profile_id=profile.id,
            store_id=store.id,
            service_id=service.id,
            service_name_snapshot=service_name,
            delivery_address_id=address.id,
            delivery_address_snapshot=address_snapshot,
            status=status,
            subtotal=subtotal,
            delivery_fee=0.0,
            tax=0.0,
            total=subtotal,
            placed_at=placed_at,
        )
        session.add(order)
        await session.flush()
        assert order.id is not None

        for item, inventory, qty in order_items:
            item.order_id = order.id
            session.add(item)
            # Cancelled orders don't consume stock.
            if status is not OrderStatus.Cancelled:
                inventory.stock = max(0, inventory.stock - qty)
                inventory.is_available = inventory.stock > 0
                session.add(inventory)

        payment = _build_demo_payment(order, payment_method, status, placed_at)
        session.add(payment)
        delivery = _build_demo_delivery(order, status, placed_at)
        session.add(delivery)
        await session.flush()


def _build_demo_payment(
    order: Order, method: PaymentMethod, status: OrderStatus, placed_at: datetime,
) -> Payment:
    """Mirror the lifecycle the checkout service drives: payment only flips
    to Paid once the order reaches Delivered (the production state machine
    treats Packed/Dispatched as fulfillment progress, not settlement)."""
    assert order.id is not None
    payment_status = PaymentStatus.Pending
    paid_at: datetime | None = None
    gateway_txn_id: str | None = None
    if status is OrderStatus.Delivered:
        payment_status = PaymentStatus.Paid
        paid_at = placed_at + timedelta(hours=6)
        if method is PaymentMethod.Upi:
            gateway_txn_id = f"DEMO-UPI-{order.id:06d}"
    elif status is OrderStatus.Cancelled:
        payment_status = PaymentStatus.Failed
    return Payment(
        order_id=order.id,
        amount=order.total,
        method=method,
        status=payment_status,
        gateway_txn_id=gateway_txn_id,
        paid_at=paid_at,
    )


def _build_demo_delivery(
    order: Order, status: OrderStatus, placed_at: datetime,
) -> Delivery:
    assert order.id is not None
    packed_at: datetime | None = None
    dispatched_at: datetime | None = None
    delivered_at: datetime | None = None
    delivery_status = DeliveryStatus.Pending
    if status is OrderStatus.Packed:
        delivery_status = DeliveryStatus.Packed
        packed_at = placed_at + timedelta(minutes=30)
    elif status is OrderStatus.Dispatched:
        delivery_status = DeliveryStatus.Dispatched
        packed_at = placed_at + timedelta(minutes=30)
        dispatched_at = placed_at + timedelta(hours=2)
    elif status is OrderStatus.Delivered:
        delivery_status = DeliveryStatus.Delivered
        packed_at = placed_at + timedelta(minutes=30)
        dispatched_at = placed_at + timedelta(hours=2)
        delivered_at = placed_at + timedelta(hours=6)
    elif status is OrderStatus.Cancelled:
        delivery_status = DeliveryStatus.Cancelled
    return Delivery(
        order_id=order.id,
        status=delivery_status,
        packed_at=packed_at,
        dispatched_at=dispatched_at,
        delivered_at=delivered_at,
    )


async def seed_seller_application_subset(session: AsyncSession) -> None:
    await _ensure_languages(session)
    admin_user = await _upsert_user(session, ADMIN["email"], ADMIN["role"])
    await _upsert_admin_profile(session, admin_user, ADMIN)
    for sort_order, service_data in enumerate(SERVICES):
        await _ensure_service(session, service_data, sort_order)
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
    for customer_data in CUSTOMERS:
        customer_profile = await _upsert_customer_profile(
            session, users_by_email[customer_data["email"]], customer_data
        )
        await _upsert_customer_addresses(
            session, customer_profile, customer_data.get("addresses", []),
        )

    services_by_slug: dict[str, Service] = {}
    for sort_order, service_data in enumerate(SERVICES):
        service = await _ensure_service(session, service_data, sort_order)
        assert service.id is not None
        services_by_slug[service.slug] = service

    for profile_data in STORE_OWNER_PROFILES:
        user = users_by_email[profile_data["email"]]
        await _upsert_seller_profile(session, user, profile_data)

    for application in APPLICATIONS:
        user = await _upsert_user(session, application["email"], UserRole.Seller)
        users_by_email[user.email] = user
        await _upsert_seller_profile(session, user, application)

    categories_by_slug: dict[str, Category] = {}
    for sort_order, category_data in enumerate(CATEGORIES):
        service = services_by_slug[category_data["service_slug"]]
        assert service.id is not None
        category = await _upsert_category(session, service.id, category_data, sort_order)
        categories_by_slug[category.slug] = category

    subcategories_by_slug: dict[str, Subcategory] = {}
    for sort_order, sub_data in enumerate(SUBCATEGORIES):
        category = categories_by_slug[sub_data["category_slug"]]
        assert category.id is not None
        sub = await _upsert_subcategory(session, category.id, sub_data, sort_order)
        subcategories_by_slug[sub.slug] = sub

    products_by_slug: dict[str, MasterProduct] = {}
    for product_data in PRODUCTS:
        sub = subcategories_by_slug[product_data["subcategory_slug"]]
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

    await _seed_demo_orders(session)

    await verify_expected_counts(session)


_COUNT_MODELS = {
    "users": User,
    "language": Language,
    "customerprofile": CustomerProfile,
    "customeraddress": CustomerAddress,
    "adminprofile": AdminProfile,
    "sellerprofile": SellerProfile,
    "sellerprofile_service": SellerProfileService,
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
    "order": Order,
    "orderitem": OrderItem,
    "payment": Payment,
    "delivery": Delivery,
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
