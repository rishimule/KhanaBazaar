from typing import Any, AsyncGenerator, Iterator

import pytest
from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_seller, get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import (
    Category,
    MasterProduct,
    MasterProductTranslation,
    Service,
    ServiceTranslation,
    Subcategory,
)
from app.models.profile import (
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store
from app.services.inventory import assert_products_in_seller_services
from tests._helpers import make_address

mock_seller = User(id=2, email="seller@kb.com", role=UserRole.Seller, is_active=True)


@pytest.fixture
async def seeded(session: AsyncSession) -> AsyncGenerator[dict[str, Any], None]:
    """Seller approved for Grocery only; 1 grocery product, 1 pharmacy product."""
    session.add(User(**mock_seller.model_dump()))
    await session.flush()

    address = Address(**make_address())
    session.add(address)
    await session.flush()

    profile = SellerProfile(
        user_id=mock_seller.id,
        first_name="S",
        business_name="S Store",
        phone="+919811110000",
        gst_number="06AAAAA1111A1Z1",
        fssai_license="44556677889900",
        bank_account_number="80100200300700",
        bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=address.id,
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

    grocery_cat = Category(slug="staples", service_id=grocery.id)
    pharmacy_cat = Category(slug="otc", service_id=pharmacy.id)
    session.add_all([grocery_cat, pharmacy_cat])
    await session.flush()

    grocery_sub = Subcategory(slug="atta", category_id=grocery_cat.id)
    pharmacy_sub = Subcategory(slug="painkillers", category_id=pharmacy_cat.id)
    session.add_all([grocery_sub, pharmacy_sub])
    await session.flush()

    atta = MasterProduct(
        subcategory_id=grocery_sub.id, slug="atta-5kg", base_price=280.0
    )
    paracetamol = MasterProduct(
        subcategory_id=pharmacy_sub.id, slug="paracetamol-500", base_price=20.0
    )
    session.add_all([atta, paracetamol])
    await session.flush()
    session.add_all(
        [
            MasterProductTranslation(
                master_product_id=atta.id,
                language_code="en",
                name="Aashirvaad Atta 5kg",
                description="5kg whole wheat flour",
            ),
            MasterProductTranslation(
                master_product_id=paracetamol.id,
                language_code="en",
                name="Paracetamol 500mg",
                description="500mg painkiller",
            ),
        ]
    )

    store_address = Address(**make_address())
    session.add(store_address)
    await session.flush()
    store = Store(
        name="S Store",
        seller_profile_id=profile.id,
        address_id=store_address.id,
    )
    session.add(store)
    await session.flush()

    # Capture IDs before commit (commit expires all instance attributes,
    # and lazy-reload mid-fixture would block on sync IO).
    ids = {
        "profile_id": profile.id,
        "store_id": store.id,
        "grocery_product_id": atta.id,
        "pharmacy_product_id": paracetamol.id,
    }
    await session.commit()

    yield ids


@pytest.fixture
def override_as_seller() -> Iterator[None]:
    app.dependency_overrides[get_current_seller] = lambda: mock_seller
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    yield
    app.dependency_overrides.pop(get_current_seller, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_assert_products_passes_for_approved_service(
    session: AsyncSession, seeded: dict[str, Any]
) -> None:
    await assert_products_in_seller_services(
        session, seeded["profile_id"], [seeded["grocery_product_id"]]
    )


@pytest.mark.asyncio
async def test_assert_products_rejects_unapproved_service(
    session: AsyncSession, seeded: dict[str, Any]
) -> None:
    with pytest.raises(HTTPException) as exc:
        await assert_products_in_seller_services(
            session,
            seeded["profile_id"],
            [seeded["grocery_product_id"], seeded["pharmacy_product_id"]],
        )
    assert exc.value.status_code == 403
    assert "SERVICE_NOT_APPROVED" in str(exc.value.detail)
