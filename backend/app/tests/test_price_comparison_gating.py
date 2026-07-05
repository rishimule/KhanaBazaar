# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import (
    Category,
    CategoryTranslation,
    MasterProduct,
    MasterProductTranslation,
    Service,
    ServiceTranslation,
    Subcategory,
    SubcategoryTranslation,
)
from app.models.platform_fee import ArrangementStatus, FeeArrangement, FeeModel
from app.models.profile import SellerProfile, SellerProfileService, VerificationStatus
from app.models.store import Store, StoreInventory
from app.schemas.price_comparison import ComparisonAlternative
from app.services.price_comparison import find_alternatives, rank_candidates
from tests._helpers import make_address


def _alt(store_id: int, total: float, dist: float, *, is_freebie: bool) -> ComparisonAlternative:
    return ComparisonAlternative(
        id=store_id, name=f"S{store_id}", distance_km=dist,
        covered_count=1, missing_count=0, covered_subtotal=total,
        imputed_subtotal=0.0, effective_total=total, items=[], is_freebie=is_freebie,
    )


def test_freebie_ranked_after_paid_even_if_cheaper() -> None:
    # Freebie store is cheaper (100) but must rank AFTER the paid store (150).
    freebie = _alt(1, 100.0, 1.0, is_freebie=True)
    paid = _alt(2, 150.0, 9.0, is_freebie=False)
    ranked = rank_candidates([freebie, paid])
    assert [a.id for a in ranked] == [2, 1]


def test_within_group_still_sorts_by_total_then_distance() -> None:
    a = _alt(1, 100.0, 5.0, is_freebie=False)
    b = _alt(2, 90.0, 9.0, is_freebie=False)
    ranked = rank_candidates([a, b])
    assert [a_.id for a_ in ranked] == [2, 1]  # cheaper first, both paid


def test_all_freebie_preserves_total_then_distance_order() -> None:
    # The current-prod case (everything freebie) must behave exactly as before.
    a = _alt(1, 100.0, 5.0, is_freebie=True)
    b = _alt(2, 90.0, 9.0, is_freebie=True)
    ranked = rank_candidates([a, b])
    assert [a_.id for a_ in ranked] == [2, 1]


# ---------------------------------------------------------------------------
# Integration: find_alternatives excludes a Suspended (store, service)
# arrangement from the candidate pool entirely.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_alternatives_excludes_suspended_store(session: AsyncSession) -> None:
    seller_x = User(id=601, email="pcg-sellerX@kb.com", role=UserRole.Seller, is_active=True)
    seller_y = User(id=602, email="pcg-sellerY@kb.com", role=UserRole.Seller, is_active=True)
    session.add_all([seller_x, seller_y])
    await session.flush()

    def _seller_addr(lat: float, lng: float) -> Address:
        return Address(**make_address(latitude=lat, longitude=lng, pincode="400018"))

    addr_x = _seller_addr(19.0078, 72.8175)
    addr_y = _seller_addr(19.0150, 72.8200)
    session.add_all([addr_x, addr_y])
    await session.flush()

    seller_profile_x = SellerProfile(
        user_id=seller_x.id, first_name="X",
        phone="+919811000601", business_name="SellerX",
        bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=addr_x.id,
    )
    seller_profile_y = SellerProfile(
        user_id=seller_y.id, first_name="Y",
        phone="+919811000602", business_name="SellerY",
        bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=addr_y.id,
    )
    session.add_all([seller_profile_x, seller_profile_y])
    await session.flush()

    store_addr_x = Address(**make_address(latitude=19.0078, longitude=72.8175, pincode="400018"))
    store_addr_y = Address(**make_address(latitude=19.0150, longitude=72.8200, pincode="400018"))
    session.add_all([store_addr_x, store_addr_y])
    await session.flush()

    store_x = Store(
        name="StoreX", seller_profile_id=seller_profile_x.id,
        address_id=store_addr_x.id, delivery_radius_km=5.0,
    )
    store_y = Store(
        name="StoreY", seller_profile_id=seller_profile_y.id,
        address_id=store_addr_y.id, delivery_radius_km=5.0,
    )
    session.add_all([store_x, store_y])
    await session.flush()

    grocery = Service(slug="pcg-grocery")
    session.add(grocery)
    await session.flush()
    session.add(ServiceTranslation(service_id=grocery.id, language_code="en", name="Grocery"))
    await session.flush()

    session.add_all([
        SellerProfileService(seller_profile_id=seller_profile_x.id, service_id=grocery.id),
        SellerProfileService(seller_profile_id=seller_profile_y.id, service_id=grocery.id),
    ])
    await session.flush()

    cat = Category(service_id=grocery.id, slug="pcg-cat1")
    session.add(cat)
    await session.flush()
    session.add(CategoryTranslation(category_id=cat.id, language_code="en", name="Cat1"))
    sub = Subcategory(category_id=cat.id, slug="pcg-sub1")
    session.add(sub)
    await session.flush()
    session.add(SubcategoryTranslation(subcategory_id=sub.id, language_code="en", name="Sub1"))

    product = MasterProduct(subcategory_id=sub.id, slug="pcg-p1", base_price=100.0)
    session.add(product)
    await session.flush()
    session.add(MasterProductTranslation(
        master_product_id=product.id, language_code="en", name="Product1", description="Product1",
    ))
    await session.flush()

    inv_x = StoreInventory(
        store_id=store_x.id, product_id=product.id, price=100.0, stock=10, is_available=True,
    )
    inv_y = StoreInventory(
        store_id=store_y.id, product_id=product.id, price=90.0, stock=10, is_available=True,
    )
    session.add_all([inv_x, inv_y])
    await session.flush()

    # Suspend StoreX for the compared service; StoreY has no arrangement
    # (defaults to freebie, must remain in the candidate pool).
    session.add(FeeArrangement(
        store_id=store_x.id, service_id=grocery.id,
        model=FeeModel.Subscription, status=ArrangementStatus.Suspended,
    ))
    await session.flush()

    assert store_x.id is not None
    assert store_y.id is not None
    assert grocery.id is not None
    store_x_id, store_y_id, service_id = store_x.id, store_y.id, grocery.id
    product_id = product.id
    assert product_id is not None

    await session.commit()

    result = await find_alternatives(
        session,
        source_store_id=999999,  # not one of the seeded stores
        service_id=service_id,
        cart_items=[(product_id, 1)],
        customer_latitude=19.0080,
        customer_longitude=72.8170,
        language_code="en",
    )

    result_ids = [a.id for a in result]
    assert store_x_id not in result_ids
    assert store_y_id in result_ids
