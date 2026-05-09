# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Any, AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_seller, get_current_user
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
from app.models.profile import (
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from app.services.eligible_products import list_eligible_products
from tests._helpers import make_address


@pytest.fixture
async def fixt(session: AsyncSession) -> AsyncGenerator[dict[str, Any], None]:
    """Seller approved for Grocery only.

    Two grocery products (one already in inventory), one pharmacy product.
    """
    user = User(email="seller@kb.com", role=UserRole.Seller, is_active=True)
    session.add(user)
    await session.flush()

    addr = Address(**make_address())
    session.add(addr)
    await session.flush()

    profile = SellerProfile(
        user_id=user.id,
        first_name="S",
        business_name="S Store",
        phone="+919811110000",
        gst_number="06AAAAA1111A1Z1",
        fssai_license="44556677889900",
        bank_account_number="80100200300700",
        bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=addr.id,
    )
    session.add(profile)
    await session.flush()

    grocery = Service(slug="grocery")
    pharmacy = Service(slug="pharmacy")
    session.add_all([grocery, pharmacy])
    await session.flush()
    session.add_all(
        [
            ServiceTranslation(
                service_id=grocery.id, language_code="en", name="Grocery"
            ),
            ServiceTranslation(
                service_id=pharmacy.id, language_code="en", name="Pharmacy"
            ),
            SellerProfileService(
                seller_profile_id=profile.id, service_id=grocery.id
            ),
        ]
    )

    cat_g = Category(slug="staples", service_id=grocery.id)
    cat_p = Category(slug="otc", service_id=pharmacy.id)
    session.add_all([cat_g, cat_p])
    await session.flush()
    session.add_all(
        [
            CategoryTranslation(
                category_id=cat_g.id,
                language_code="en",
                name="Staples",
                description="Staple foods",
            ),
            CategoryTranslation(
                category_id=cat_p.id,
                language_code="en",
                name="OTC",
                description="Over the counter",
            ),
        ]
    )

    sub_g = Subcategory(slug="atta-fixt", category_id=cat_g.id)
    sub_p = Subcategory(slug="pain-fixt", category_id=cat_p.id)
    session.add_all([sub_g, sub_p])
    await session.flush()
    session.add_all(
        [
            SubcategoryTranslation(
                subcategory_id=sub_g.id,
                language_code="en",
                name="Atta",
                description="Flour",
            ),
            SubcategoryTranslation(
                subcategory_id=sub_p.id,
                language_code="en",
                name="Painkillers",
                description="Pain meds",
            ),
        ]
    )

    atta = MasterProduct(subcategory_id=sub_g.id, slug="atta-eligible", base_price=280.0)
    salt = MasterProduct(subcategory_id=sub_g.id, slug="salt-eligible", base_price=22.0)
    paracetamol = MasterProduct(
        subcategory_id=sub_p.id, slug="para-eligible", base_price=20.0
    )
    session.add_all([atta, salt, paracetamol])
    await session.flush()
    session.add_all(
        [
            MasterProductTranslation(
                master_product_id=atta.id,
                language_code="en",
                name="Aashirvaad Atta 5kg",
                description="5kg flour",
            ),
            MasterProductTranslation(
                master_product_id=salt.id,
                language_code="en",
                name="Tata Salt 1kg",
                description="iodized",
            ),
            MasterProductTranslation(
                master_product_id=paracetamol.id,
                language_code="en",
                name="Paracetamol 500mg",
                description="painkiller",
            ),
        ]
    )

    store_addr = Address(**make_address())
    session.add(store_addr)
    await session.flush()
    store = Store(
        name="S Store", seller_profile_id=profile.id, address_id=store_addr.id
    )
    session.add(store)
    await session.flush()
    session.add(
        StoreInventory(
            store_id=store.id, product_id=atta.id, price=275.0, stock=10
        )
    )
    await session.flush()

    ids = {
        "user_id": user.id,
        "profile_id": profile.id,
        "store_id": store.id,
        "atta_id": atta.id,
        "salt_id": salt.id,
        "paracetamol_id": paracetamol.id,
    }
    await session.commit()

    yield ids


@pytest.mark.asyncio
async def test_list_eligible_filters_unapproved_services(
    session: AsyncSession, fixt: dict[str, Any]
) -> None:
    rows = await list_eligible_products(
        session, profile_id=fixt["profile_id"], store_id=fixt["store_id"], lang="en"
    )
    ids = {r.id for r in rows}
    assert fixt["atta_id"] in ids
    assert fixt["salt_id"] in ids
    assert fixt["paracetamol_id"] not in ids


@pytest.mark.asyncio
async def test_list_eligible_marks_in_inventory(
    session: AsyncSession, fixt: dict[str, Any]
) -> None:
    rows = await list_eligible_products(
        session, profile_id=fixt["profile_id"], store_id=fixt["store_id"], lang="en"
    )
    by_id = {r.id: r for r in rows}
    assert by_id[fixt["atta_id"]].in_inventory is True
    assert by_id[fixt["salt_id"]].in_inventory is False


@pytest.fixture
def override_as_user(fixt: dict[str, Any]) -> Iterator[None]:
    user = User(
        id=fixt["user_id"],
        email="seller@kb.com",
        role=UserRole.Seller,
        is_active=True,
    )
    app.dependency_overrides[get_current_seller] = lambda: user
    app.dependency_overrides[get_current_user] = lambda: user
    yield
    app.dependency_overrides.pop(get_current_seller, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_eligible_products_endpoint_returns_filtered_list(
    fixt: dict[str, Any], override_as_user: None
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/sellers/me/eligible-products")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids = {p["id"] for p in body}
        assert fixt["atta_id"] in ids
        assert fixt["salt_id"] in ids
        assert fixt["paracetamol_id"] not in ids
