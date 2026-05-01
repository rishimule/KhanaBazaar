from sqlalchemy import inspect

from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import (
    Category,
    CategoryTranslation,
    Language,
    LanguageCode,
    MasterProduct,
    MasterProductTranslation,
    Service,
    ServiceTranslation,
    Subcategory,
    SubcategoryTranslation,
)
from app.models.commerce import (
    Cart,
    CartItem,
    Delivery,
    Favorite,
    Order,
    OrderItem,
    Payment,
    Review,
)
from app.models.profile import (
    AdminProfile,
    CustomerAddress,
    CustomerProfile,
    SellerProfile,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory


def test_core_enum_values_are_api_values() -> None:
    assert [role.value for role in UserRole] == ["customer", "seller", "admin"]
    assert [language.value for language in LanguageCode] == ["en", "hi", "mr", "gu", "pa"]
    assert [status.value for status in VerificationStatus] == ["pending", "approved", "rejected"]


def test_expected_tables_are_registered_in_metadata() -> None:
    expected = {
        "user",
        "language",
        "customerprofile",
        "adminprofile",
        "sellerprofile",
        "address",
        "customeraddress",
        "service",
        "service_translation",
        "category",
        "category_translation",
        "subcategory",
        "subcategory_translation",
        "masterproduct",
        "masterproduct_translation",
        "store",
        "storeinventory",
        "cart",
        "cartitem",
        "order",
        "orderitem",
        "payment",
        "delivery",
        "review",
        "favorite",
    }
    assert expected.issubset(User.metadata.tables.keys())


def test_new_schema_columns_are_present() -> None:
    user_columns = {column.name for column in inspect(User).columns}
    assert {"email", "hashed_password", "is_active", "role", "preferred_language"}.issubset(user_columns)
    assert "full_name" not in user_columns

    seller_columns = {column.name for column in inspect(SellerProfile).columns}
    assert {
        "user_id",
        "first_name",
        "last_name",
        "business_name",
        "business_category",
        "business_address_id",
        "verification_status",
    }.issubset(seller_columns)
    assert "address_line1" not in seller_columns

    product_columns = {column.name for column in inspect(MasterProduct).columns}
    assert {"subcategory_id", "slug", "image_url", "base_price"}.issubset(product_columns)
    assert "name" not in product_columns

    store_columns = {column.name for column in inspect(Store).columns}
    assert {"seller_profile_id", "address_id", "name", "is_active"}.issubset(store_columns)
    assert "seller_id" not in store_columns
    assert "address_line1" not in store_columns


def test_model_classes_are_imported() -> None:
    classes = [
        Address,
        CustomerProfile,
        CustomerAddress,
        AdminProfile,
        SellerProfile,
        Language,
        Service,
        ServiceTranslation,
        Category,
        CategoryTranslation,
        Subcategory,
        SubcategoryTranslation,
        MasterProduct,
        MasterProductTranslation,
        Store,
        StoreInventory,
        Cart,
        CartItem,
        Order,
        OrderItem,
        Payment,
        Delivery,
        Review,
        Favorite,
    ]
    assert all(getattr(model, "__table__", None) is not None for model in classes)
