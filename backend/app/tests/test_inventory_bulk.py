# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Any, AsyncGenerator, Iterator

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
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
from app.models.store import Store, StoreInventory
from app.schemas.inventory import BulkInventoryItem
from app.services.inventory import (
    assert_products_in_seller_services,
    bulk_upsert_inventory,
)
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


@pytest.mark.asyncio
async def test_bulk_upsert_creates_and_updates_in_one_call(
    session: AsyncSession, seeded: dict[str, Any]
) -> None:
    # Pre-existing row for the grocery product.
    existing = StoreInventory(
        store_id=seeded["store_id"],
        product_id=seeded["grocery_product_id"],
        price=200.0,
        stock=5,
        is_available=True,
    )
    session.add(existing)
    await session.commit()

    # Add a second grocery product (sharing the grocery subcategory) so we
    # have an insert candidate alongside the update candidate above.
    existing_product = await session.get(MasterProduct, seeded["grocery_product_id"])
    assert existing_product is not None
    second_grocery = MasterProduct(
        subcategory_id=existing_product.subcategory_id,
        slug="tata-salt-1kg",
        base_price=22.0,
    )
    session.add(second_grocery)
    await session.flush()
    session.add(
        MasterProductTranslation(
            master_product_id=second_grocery.id,
            language_code="en",
            name="Tata Salt 1kg",
            description="iodized salt",
        )
    )
    assert second_grocery.id is not None
    second_id: int = second_grocery.id
    await session.commit()

    items = [
        BulkInventoryItem(
            product_id=seeded["grocery_product_id"],
            price=275.0, stock=50, is_available=True,
        ),
        BulkInventoryItem(
            product_id=second_id,
            price=22.0, stock=120, is_available=True,
        ),
    ]

    rows = await bulk_upsert_inventory(session, seeded["store_id"], items)
    await session.commit()

    assert len(rows) == 2
    db_rows = list((await session.exec(
        select(StoreInventory).where(StoreInventory.store_id == seeded["store_id"])
    )).all())
    by_product = {r.product_id: r for r in db_rows}
    assert by_product[seeded["grocery_product_id"]].price == 275.0
    assert by_product[seeded["grocery_product_id"]].stock == 50
    assert by_product[second_id].price == 22.0
    assert by_product[second_id].stock == 120
    # The existing row was updated, not duplicated:
    assert len(db_rows) == 2


@pytest.mark.asyncio
async def test_bulk_upsert_dedup_last_wins(
    session: AsyncSession, seeded: dict[str, Any]
) -> None:
    items = [
        BulkInventoryItem(
            product_id=seeded["grocery_product_id"], price=100.0, stock=10
        ),
        BulkInventoryItem(
            product_id=seeded["grocery_product_id"], price=200.0, stock=20
        ),
    ]
    rows = await bulk_upsert_inventory(session, seeded["store_id"], items)
    assert len(rows) == 1
    assert rows[0].price == 200.0
    assert rows[0].stock == 20
    await session.commit()

    db_rows = list((await session.exec(
        select(StoreInventory).where(StoreInventory.store_id == seeded["store_id"])
    )).all())
    assert len(db_rows) == 1
    assert db_rows[0].price == 200.0


@pytest.mark.asyncio
async def test_bulk_endpoint_creates_and_updates_atomically(
    seeded: dict[str, Any], override_as_seller: None
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "items": [
                {
                    "product_id": seeded["grocery_product_id"],
                    "price": 275.0,
                    "stock": 50,
                    "is_available": True,
                },
            ]
        }
        resp = await ac.put(
            f"/api/v1/stores/{seeded['store_id']}/inventory/bulk", json=payload
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body) == 1
        assert body[0]["price"] == 275.0
        assert body[0]["stock"] == 50


@pytest.mark.asyncio
async def test_bulk_endpoint_rejects_unapproved_service(
    seeded: dict[str, Any], override_as_seller: None
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "items": [
                {
                    "product_id": seeded["pharmacy_product_id"],
                    "price": 20.0,
                    "stock": 5,
                    "is_available": True,
                },
            ]
        }
        resp = await ac.put(
            f"/api/v1/stores/{seeded['store_id']}/inventory/bulk", json=payload
        )
        assert resp.status_code == 403, resp.text
        assert "SERVICE_NOT_APPROVED" in resp.text


@pytest.mark.asyncio
async def test_bulk_endpoint_caps_at_200_rows(
    seeded: dict[str, Any], override_as_seller: None
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        items = [
            {
                "product_id": seeded["grocery_product_id"],
                "price": 1.0,
                "stock": 1,
                "is_available": True,
            }
            for _ in range(201)
        ]
        resp = await ac.put(
            f"/api/v1/stores/{seeded['store_id']}/inventory/bulk",
            json={"items": items},
        )
        assert resp.status_code == 422, resp.text
        assert "ROW_LIMIT" in resp.text


@pytest.mark.asyncio
async def test_bulk_endpoint_rejects_invalid_price(
    seeded: dict[str, Any], override_as_seller: None
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "items": [
                {
                    "product_id": seeded["grocery_product_id"],
                    "price": 0.0,
                    "stock": 5,
                    "is_available": True,
                },
            ]
        }
        resp = await ac.put(
            f"/api/v1/stores/{seeded['store_id']}/inventory/bulk", json=payload
        )
        assert resp.status_code == 422, resp.text
        assert "PRICE_INVALID" in resp.text


@pytest.mark.asyncio
async def test_bulk_endpoint_rolls_back_on_invalid_row(
    session: AsyncSession,
    seeded: dict[str, Any],
    override_as_seller: None,
) -> None:
    """One invalid row → entire batch rejected, DB unchanged."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "items": [
                {
                    "product_id": seeded["grocery_product_id"],
                    "price": 99.0,
                    "stock": 9,
                    "is_available": True,
                },
                {
                    "product_id": seeded["pharmacy_product_id"],
                    "price": 99.0,
                    "stock": 9,
                    "is_available": True,
                },
            ]
        }
        resp = await ac.put(
            f"/api/v1/stores/{seeded['store_id']}/inventory/bulk", json=payload
        )
        assert resp.status_code == 403

    rows = list((await session.exec(
        select(StoreInventory).where(StoreInventory.store_id == seeded["store_id"])
    )).all())
    assert rows == []


@pytest.mark.asyncio
async def test_single_post_inventory_now_enforces_service_membership(
    seeded: dict[str, Any], override_as_seller: None
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "product_id": seeded["pharmacy_product_id"],
            "price": 20.0,
            "stock": 5,
            "is_available": True,
            "store_id": seeded["store_id"],
        }
        resp = await ac.post(
            f"/api/v1/stores/{seeded['store_id']}/inventory", json=payload
        )
        assert resp.status_code == 403, resp.text
        assert "SERVICE_NOT_APPROVED" in resp.text
