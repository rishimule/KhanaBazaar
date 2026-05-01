# Customer Account Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a customer-only account area at `/account/settings` where customers can update basic profile details and manage saved delivery addresses.

**Architecture:** The backend gets a new `/api/v1/customers` router guarded by a customer-only auth dependency and backed by the existing `CustomerProfile`, `CustomerAddress`, `Address`, and `AddressPayload` models. The frontend adds an account dashboard shell that reuses the existing dashboard layout, then builds one settings page that fetches the full customer profile, saves profile changes, and updates address state from mutation responses.

**Tech Stack:** FastAPI, SQLModel, Pydantic v2, Pytest, httpx, Next.js 16 App Router, React 19, TypeScript, CSS Modules.

**Reference Spec:** `docs/superpowers/specs/2026-05-01-customer-account-settings-design.md`

---

## File Structure

### Backend

- **Modify:** `backend/app/src/app/core/security.py` — make missing bearer credentials return `401`, and add `get_current_customer`.
- **Create:** `backend/app/src/app/schemas/customers.py` — customer profile/address response models and mutation request models.
- **Create:** `backend/app/src/app/api/customers.py` — `/customers/me` profile endpoint and saved-address endpoints.
- **Modify:** `backend/app/src/app/api/__init__.py` — mount the customer router under `/customers`.
- **Create:** `backend/app/tests/test_customers.py` — access control, profile update, address create/update/delete/default tests.

### Frontend

- **Modify:** `frontend/src/types/index.ts` — add `CustomerAddress` and `CustomerProfile`.
- **Modify:** `frontend/src/components/DashboardLayout.tsx` — allow the existing dashboard shell to render a customer account role.
- **Modify:** `frontend/src/components/DashboardLayout.module.css` — add customer icon styling.
- **Create:** `frontend/src/app/account/layout.tsx` — client-side account guard and dashboard shell.
- **Create:** `frontend/src/app/account/page.tsx` — redirect `/account` to `/account/settings`.
- **Create:** `frontend/src/app/account/settings/page.tsx` — profile form and address management UI.
- **Create:** `frontend/src/app/account/settings/page.module.css` — account settings page styles.

No database migration is expected. The existing schema already has `customerprofile`, `customeraddress`, and `address`.

---

## Task 1: Backend customer tests

**Files:**
- Create: `backend/app/tests/test_customers.py`

- [ ] **Step 1: Write the failing customer router test file**

Create `backend/app/tests/test_customers.py`:

```python
from collections.abc import AsyncGenerator, Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.profile import CustomerAddress, CustomerProfile, SellerProfile, VerificationStatus
from tests._helpers import make_address

mock_customer = User(id=101, email="customer@kb.com", role=UserRole.Customer, is_active=True)
mock_other_customer = User(id=102, email="other@kb.com", role=UserRole.Customer, is_active=True)
mock_seller = User(id=103, email="seller-customer-api@kb.com", role=UserRole.Seller, is_active=True)
mock_admin = User(id=104, email="admin-customer-api@kb.com", role=UserRole.Admin, is_active=True)
mock_orphan_customer = User(id=105, email="orphan@kb.com", role=UserRole.Customer, is_active=True)


async def _seed_customer_profile(
    session: AsyncSession,
    user: User,
    first_name: str,
    last_name: str | None,
    phone: str | None,
) -> CustomerProfile:
    profile = CustomerProfile(
        user_id=user.id,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
    )
    session.add(profile)
    await session.flush()
    return profile


async def _seed_customer_address(
    session: AsyncSession,
    profile: CustomerProfile,
    *,
    label: str | None = "Home",
    is_default: bool = False,
    pincode: str = "122001",
) -> CustomerAddress:
    address = Address(**make_address(pincode=pincode))
    session.add(address)
    await session.flush()
    customer_address = CustomerAddress(
        customer_profile_id=profile.id,
        address_id=address.id,
        label=label,
        is_default=is_default,
    )
    session.add(customer_address)
    await session.flush()
    return customer_address


@pytest.fixture(autouse=True)
async def seed_users_and_profiles(session: AsyncSession) -> AsyncGenerator[None, None]:
    session.add(User(**mock_customer.model_dump()))
    session.add(User(**mock_other_customer.model_dump()))
    session.add(User(**mock_seller.model_dump()))
    session.add(User(**mock_admin.model_dump()))
    session.add(User(**mock_orphan_customer.model_dump()))
    await session.flush()

    customer_profile = await _seed_customer_profile(
        session,
        mock_customer,
        first_name="Asha",
        last_name="Patel",
        phone="9876543210",
    )
    other_profile = await _seed_customer_profile(
        session,
        mock_other_customer,
        first_name="Other",
        last_name=None,
        phone="9876543211",
    )
    await _seed_customer_address(
        session,
        customer_profile,
        label="Home",
        is_default=True,
        pincode="122001",
    )
    await _seed_customer_address(
        session,
        other_profile,
        label="Other Home",
        is_default=False,
        pincode="400001",
    )

    seller_address = Address(**make_address(pincode="560001"))
    session.add(seller_address)
    await session.flush()
    session.add(
        SellerProfile(
            user_id=mock_seller.id,
            first_name="Seller",
            last_name="User",
            business_name="Seller Store",
            business_category="grocery",
            phone="+919811110000",
            gst_number="06AAAAA1111A1Z1",
            fssai_license="44556677889900",
            bank_account_number="80100200300700",
            bank_ifsc="HDFC0000001",
            verification_status=VerificationStatus.Approved,
            business_address_id=seller_address.id,
        )
    )

    await session.commit()
    yield


@pytest.fixture
def override_as_customer() -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: mock_customer
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def override_as_other_customer() -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: mock_other_customer
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def override_as_seller() -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def override_as_admin() -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def override_as_orphan_customer() -> Iterator[None]:
    app.dependency_overrides[get_current_user] = lambda: mock_orphan_customer
    yield
    app.dependency_overrides.pop(get_current_user, None)


async def test_guest_cannot_fetch_customer_profile() -> None:
    app.dependency_overrides.pop(get_current_user, None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/customers/me")
    assert resp.status_code == 401


async def test_seller_cannot_fetch_customer_profile(override_as_seller: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/customers/me")
    assert resp.status_code == 403


async def test_admin_cannot_fetch_customer_profile(override_as_admin: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/customers/me")
    assert resp.status_code == 403


async def test_customer_without_profile_returns_404(override_as_orphan_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/customers/me")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Customer profile not found"}


async def test_customer_can_fetch_profile(override_as_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/customers/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == mock_customer.id
    assert data["email"] == "customer@kb.com"
    assert data["first_name"] == "Asha"
    assert data["last_name"] == "Patel"
    assert data["phone"] == "9876543210"
    assert len(data["addresses"]) == 1
    assert data["addresses"][0]["label"] == "Home"
    assert data["addresses"][0]["is_default"] is True
    assert data["addresses"][0]["address"]["pincode"] == "122001"


async def test_customer_can_update_profile_fields(override_as_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            "/api/v1/customers/me",
            json={"first_name": "Priya", "last_name": None, "phone": "9876500000"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["first_name"] == "Priya"
    assert data["last_name"] is None
    assert data["phone"] == "9876500000"
    assert data["email"] == "customer@kb.com"


async def test_customer_cannot_update_email(override_as_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            "/api/v1/customers/me",
            json={"first_name": "Asha", "email": "changed@example.com"},
        )
    assert resp.status_code == 422


async def test_customer_can_add_address(override_as_customer: Any) -> None:
    payload = {
        "label": "Work",
        "is_default": False,
        "address": make_address(address_line1="55 Office Park", pincode="560001", state="Karnataka"),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/customers/me/addresses", json=payload)
    assert resp.status_code == 200
    addresses = resp.json()["addresses"]
    assert len(addresses) == 2
    assert any(addr["label"] == "Work" and addr["address"]["pincode"] == "560001" for addr in addresses)


async def test_invalid_address_payload_returns_422(override_as_customer: Any) -> None:
    payload = {
        "label": "Invalid",
        "is_default": False,
        "address": make_address(pincode="000001"),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/customers/me/addresses", json=payload)
    assert resp.status_code == 422


async def test_customer_can_edit_owned_address(override_as_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        before = await ac.get("/api/v1/customers/me")
        address_id = before.json()["addresses"][0]["id"]
        resp = await ac.put(
            f"/api/v1/customers/me/addresses/{address_id}",
            json={
                "label": "Family",
                "is_default": True,
                "address": make_address(address_line1="99 Updated Road", pincode="110001", state="Delhi"),
            },
        )
    assert resp.status_code == 200
    updated = resp.json()["addresses"][0]
    assert updated["label"] == "Family"
    assert updated["is_default"] is True
    assert updated["address"]["address_line1"] == "99 Updated Road"
    assert updated["address"]["pincode"] == "110001"


async def test_customer_cannot_edit_another_customers_address(
    override_as_customer: Any,
    session: AsyncSession,
) -> None:
    result = await session.exec(
        select(CustomerAddress)
        .join(CustomerProfile, CustomerProfile.id == CustomerAddress.customer_profile_id)
        .where(CustomerProfile.user_id == mock_other_customer.id)
    )
    other_address = result.one()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/api/v1/customers/me/addresses/{other_address.id}",
            json={
                "label": "Stolen",
                "is_default": False,
                "address": make_address(),
            },
        )
    assert resp.status_code == 404


async def test_customer_can_set_default_address(override_as_customer: Any) -> None:
    create_payload = {
        "label": "Office",
        "is_default": False,
        "address": make_address(address_line1="22 Office", pincode="560001", state="Karnataka"),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create = await ac.post("/api/v1/customers/me/addresses", json=create_payload)
        new_address = next(addr for addr in create.json()["addresses"] if addr["label"] == "Office")
        resp = await ac.post(f"/api/v1/customers/me/addresses/{new_address['id']}/default")
    assert resp.status_code == 200
    addresses = resp.json()["addresses"]
    assert sum(1 for addr in addresses if addr["is_default"]) == 1
    assert next(addr for addr in addresses if addr["label"] == "Office")["is_default"] is True
    assert next(addr for addr in addresses if addr["label"] == "Home")["is_default"] is False


async def test_creating_default_address_clears_previous_default(override_as_customer: Any) -> None:
    payload = {
        "label": "Parents",
        "is_default": True,
        "address": make_address(address_line1="1 Parent Home", pincode="400001", state="Maharashtra"),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/customers/me/addresses", json=payload)
    assert resp.status_code == 200
    addresses = resp.json()["addresses"]
    assert sum(1 for addr in addresses if addr["is_default"]) == 1
    assert next(addr for addr in addresses if addr["label"] == "Parents")["is_default"] is True


async def test_deleting_default_address_leaves_no_default(override_as_customer: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        before = await ac.get("/api/v1/customers/me")
        default_address = next(addr for addr in before.json()["addresses"] if addr["is_default"])
        resp = await ac.delete(f"/api/v1/customers/me/addresses/{default_address['id']}")
    assert resp.status_code == 200
    assert resp.json()["addresses"] == []


async def test_deleting_non_owned_address_returns_404(
    override_as_customer: Any,
    session: AsyncSession,
) -> None:
    result = await session.exec(
        select(CustomerAddress)
        .join(CustomerProfile, CustomerProfile.id == CustomerAddress.customer_profile_id)
        .where(CustomerProfile.user_id == mock_other_customer.id)
    )
    other_address = result.one()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete(f"/api/v1/customers/me/addresses/{other_address.id}")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run the new backend tests to verify they fail**

Run: `cd backend/app && uv run pytest tests/test_customers.py -v`

Expected: FAIL with `404 Not Found` for `/api/v1/customers/me` or import errors for modules that do not exist yet.

- [ ] **Step 3: Commit the failing tests**

```bash
git add backend/app/tests/test_customers.py
git commit -m "test(customers): cover customer account API"
```

---

## Task 2: Backend schemas, auth guard, and customer API

**Files:**
- Modify: `backend/app/src/app/core/security.py`
- Create: `backend/app/src/app/schemas/customers.py`
- Create: `backend/app/src/app/api/customers.py`
- Modify: `backend/app/src/app/api/__init__.py`
- Test: `backend/app/tests/test_customers.py`

- [ ] **Step 1: Update auth security for customer-only access**

Modify `backend/app/src/app/core/security.py`:

```python
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.db.session import get_db_session
from app.models.base import User, UserRole

security = HTTPBearer(auto_error=False)


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "iat": now,
        "exp": now + timedelta(hours=settings.JWT_EXPIRES_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, object]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def verify_access_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, object]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(credentials.credentials)


async def get_current_user(
    payload: dict[str, object] = Depends(verify_access_token),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing sub claim")

    statement = select(User).where(User.id == int(str(user_id)))
    result = await session.exec(statement)
    user = result.first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    return user


async def get_current_customer(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.Customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough privileges. Customer role required.",
        )
    return current_user


async def get_current_seller(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in (UserRole.Seller, UserRole.Admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough privileges. Seller role required.",
        )
    return current_user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.Admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough privileges. Admin role required.",
        )
    return current_user


def create_email_verification_token(email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "type": "seller_otp",
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_email_verification_token(token: str) -> str:
    """Validate seller OTP email token. Returns email on success. Raises HTTPException otherwise."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"error": "email_token_expired"},
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_email_token"},
        ) from None
    if payload.get("type") != "seller_otp":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_email_token"},
        )
    return str(payload["sub"])
```

- [ ] **Step 2: Create customer API schemas**

Create `backend/app/src/app/schemas/customers.py`:

```python
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.address import AddressPayload


class CustomerAddressRead(BaseModel):
    id: int
    label: str | None
    is_default: bool
    address: AddressPayload


class CustomerProfileRead(BaseModel):
    user_id: int
    email: str
    first_name: str
    last_name: str | None
    phone: str | None
    addresses: list[CustomerAddressRead]


class CustomerProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _first_name_cannot_be_null(self) -> "CustomerProfileUpdate":
        if "first_name" in self.model_fields_set and self.first_name is None:
            raise ValueError("first_name cannot be null")
        return self


class CustomerAddressWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, max_length=60)
    is_default: bool = False
    address: AddressPayload
```

- [ ] **Step 3: Create the customer router**

Create `backend/app/src/app/api/customers.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_customer
from app.db.session import get_db_session
from app.models.address import Address
from app.models.base import User
from app.models.profile import CustomerAddress, CustomerProfile
from app.schemas.address import address_from_payload, address_to_payload
from app.schemas.customers import (
    CustomerAddressRead,
    CustomerAddressWrite,
    CustomerProfileRead,
    CustomerProfileUpdate,
)

router = APIRouter()


async def _customer_profile_for_user(
    session: AsyncSession,
    user_id: int,
) -> CustomerProfile:
    result = await session.exec(
        select(CustomerProfile).where(CustomerProfile.user_id == user_id)
    )
    profile = result.first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    return profile


async def _customer_addresses(
    session: AsyncSession,
    customer_profile_id: int,
) -> list[CustomerAddress]:
    result = await session.exec(
        select(CustomerAddress)
        .where(CustomerAddress.customer_profile_id == customer_profile_id)
        .options(selectinload(CustomerAddress.address))  # type: ignore[arg-type]
        .order_by(CustomerAddress.is_default.desc(), CustomerAddress.id.asc())  # type: ignore[union-attr]
    )
    return list(result.all())


async def _profile_response(
    session: AsyncSession,
    user: User,
    profile: CustomerProfile,
) -> CustomerProfileRead:
    assert user.id is not None
    assert profile.id is not None
    addresses = await _customer_addresses(session, profile.id)
    return CustomerProfileRead(
        user_id=user.id,
        email=user.email,
        first_name=profile.first_name,
        last_name=profile.last_name,
        phone=profile.phone,
        addresses=[
            CustomerAddressRead(
                id=customer_address.id,
                label=customer_address.label,
                is_default=customer_address.is_default,
                address=address_to_payload(customer_address.address),
            )
            for customer_address in addresses
            if customer_address.id is not None
        ],
    )


async def _owned_customer_address(
    session: AsyncSession,
    profile: CustomerProfile,
    customer_address_id: int,
) -> CustomerAddress:
    assert profile.id is not None
    result = await session.exec(
        select(CustomerAddress)
        .where(
            CustomerAddress.id == customer_address_id,
            CustomerAddress.customer_profile_id == profile.id,
        )
        .options(selectinload(CustomerAddress.address))  # type: ignore[arg-type]
    )
    customer_address = result.first()
    if customer_address is None:
        raise HTTPException(status_code=404, detail="Customer address not found")
    return customer_address


async def _clear_default_addresses(
    session: AsyncSession,
    customer_profile_id: int,
) -> None:
    addresses = await _customer_addresses(session, customer_profile_id)
    for customer_address in addresses:
        customer_address.is_default = False
        session.add(customer_address)


@router.get("/me", response_model=CustomerProfileRead)
async def get_customer_profile(
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileRead:
    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)
    return await _profile_response(session, current_user, profile)


@router.patch("/me", response_model=CustomerProfileRead)
async def update_customer_profile(
    body: CustomerProfileUpdate,
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileRead:
    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)

    if body.first_name is not None:
        profile.first_name = body.first_name
    if "last_name" in body.model_fields_set:
        profile.last_name = body.last_name
    if "phone" in body.model_fields_set:
        profile.phone = body.phone

    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    await session.refresh(current_user)
    return await _profile_response(session, current_user, profile)


@router.post("/me/addresses", response_model=CustomerProfileRead)
async def create_customer_address(
    body: CustomerAddressWrite,
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileRead:
    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)
    assert profile.id is not None
    if body.is_default:
        await _clear_default_addresses(session, profile.id)

    address = Address(**address_from_payload(body.address))
    session.add(address)
    await session.flush()
    assert address.id is not None

    customer_address = CustomerAddress(
        customer_profile_id=profile.id,
        address_id=address.id,
        label=body.label,
        is_default=body.is_default,
    )
    session.add(customer_address)
    await session.commit()
    await session.refresh(profile)
    await session.refresh(current_user)
    return await _profile_response(session, current_user, profile)


@router.put("/me/addresses/{customer_address_id}", response_model=CustomerProfileRead)
async def update_customer_address(
    customer_address_id: int,
    body: CustomerAddressWrite,
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileRead:
    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)
    customer_address = await _owned_customer_address(session, profile, customer_address_id)

    if body.is_default:
        await _clear_default_addresses(session, profile.id)

    customer_address.label = body.label
    customer_address.is_default = body.is_default
    for key, value in address_from_payload(body.address).items():
        setattr(customer_address.address, key, value)

    session.add(customer_address.address)
    session.add(customer_address)
    await session.commit()
    await session.refresh(profile)
    await session.refresh(current_user)
    return await _profile_response(session, current_user, profile)


@router.delete("/me/addresses/{customer_address_id}", response_model=CustomerProfileRead)
async def delete_customer_address(
    customer_address_id: int,
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileRead:
    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)
    customer_address = await _owned_customer_address(session, profile, customer_address_id)
    address = customer_address.address

    await session.delete(customer_address)
    await session.delete(address)
    await session.commit()
    await session.refresh(profile)
    await session.refresh(current_user)
    return await _profile_response(session, current_user, profile)


@router.post("/me/addresses/{customer_address_id}/default", response_model=CustomerProfileRead)
async def set_default_customer_address(
    customer_address_id: int,
    current_user: User = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> CustomerProfileRead:
    assert current_user.id is not None
    profile = await _customer_profile_for_user(session, current_user.id)
    customer_address = await _owned_customer_address(session, profile, customer_address_id)

    await _clear_default_addresses(session, profile.id)
    customer_address.is_default = True
    session.add(customer_address)
    await session.commit()
    await session.refresh(profile)
    await session.refresh(current_user)
    return await _profile_response(session, current_user, profile)
```

- [ ] **Step 4: Mount the router**

Modify `backend/app/src/app/api/__init__.py`:

```python
from fastapi import APIRouter

from app.api import auth, catalog, customers, meta, sellers, stores, tasks

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(catalog.router, prefix="/catalog", tags=["catalog"])
api_router.include_router(stores.router, prefix="/stores", tags=["stores"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(sellers.router, prefix="/sellers", tags=["sellers"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(meta.router, prefix="/meta", tags=["meta"])
```

- [ ] **Step 5: Run the customer API tests**

Run: `cd backend/app && uv run pytest tests/test_customers.py -v`

Expected: all tests in `test_customers.py` pass.

- [ ] **Step 6: Run backend lint and focused regression tests**

Run: `cd backend/app && uv run ruff check .`

Expected: PASS with no lint errors.

Run: `cd backend/app && uv run pytest tests/test_customers.py tests/test_auth.py tests/test_stores.py -v`

Expected: all selected tests pass. This checks the new `HTTPBearer(auto_error=False)` behavior does not break existing auth/store flows.

- [ ] **Step 7: Commit the backend implementation**

```bash
git add backend/app/src/app/core/security.py backend/app/src/app/schemas/customers.py backend/app/src/app/api/customers.py backend/app/src/app/api/__init__.py
git commit -m "feat(customers): add account profile API"
```

---

## Task 3: Frontend account shell and customer types

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/DashboardLayout.tsx`
- Modify: `frontend/src/components/DashboardLayout.module.css`
- Create: `frontend/src/app/account/layout.tsx`
- Create: `frontend/src/app/account/page.tsx`

- [ ] **Step 1: Add customer account types**

Modify `frontend/src/types/index.ts` by adding these interfaces after the existing `Address` interface:

```ts
/** A saved delivery address for a customer account. */
export interface CustomerAddress {
  id: number;
  label: string | null;
  is_default: boolean;
  address: Address;
}

/** Customer profile payload returned by GET /customers/me. */
export interface CustomerProfile {
  user_id: number;
  email: string;
  first_name: string;
  last_name: string | null;
  phone: string | null;
  addresses: CustomerAddress[];
}
```

- [ ] **Step 2: Generalize the dashboard layout role**

Modify `frontend/src/components/DashboardLayout.tsx`:

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import styles from "./DashboardLayout.module.css";

interface NavItem {
  href: string;
  label: string;
  icon: string;
}

type DashboardRole = "seller" | "admin" | "customer";

interface Props {
  children: React.ReactNode;
  role: DashboardRole;
  roleName: string;
  title: string;
  navItems: NavItem[];
}

const ROLE_LABELS: Record<DashboardRole, string> = {
  seller: "Seller Portal",
  admin: "Admin Panel",
  customer: "Account",
};

const ROLE_ICONS: Record<DashboardRole, string> = {
  seller: "🏪",
  admin: "⚙️",
  customer: "👤",
};

const ROLE_ICON_CLASSES: Record<DashboardRole, string> = {
  seller: styles.roleIconSeller,
  admin: styles.roleIconAdmin,
  customer: styles.roleIconCustomer,
};

export default function DashboardLayout({
  children,
  role,
  roleName,
  title,
  navItems,
}: Props) {
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className={styles.dashboard}>
      {sidebarOpen && (
        <div className={styles.overlay} onClick={() => setSidebarOpen(false)} />
      )}
      <aside
        className={`${styles.sidebar} ${sidebarOpen ? styles.sidebarOpen : ""}`}
      >
        <div className={styles.sidebarHeader}>
          <div className={`${styles.roleIcon} ${ROLE_ICON_CLASSES[role]}`}>
            {ROLE_ICONS[role]}
          </div>
          <div className={styles.roleInfo}>
            <span className={styles.roleName}>{roleName}</span>
            <span className={styles.roleLabel}>{ROLE_LABELS[role]}</span>
          </div>
        </div>

        <nav className={styles.sidebarNav}>
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`${styles.sidebarLink} ${
                pathname === item.href ? styles.sidebarLinkActive : ""
              }`}
              onClick={() => setSidebarOpen(false)}
            >
              <span className={styles.sidebarLinkIcon}>{item.icon}</span>
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>

      <div className={styles.main}>
        <div className={styles.topBar}>
          <div className={styles.topBarActions}>
            <button
              className={styles.mobileToggle}
              onClick={() => setSidebarOpen(true)}
              aria-label="Open sidebar"
            >
              ☰
            </button>
            <h1 className={styles.topBarTitle}>{title}</h1>
          </div>
        </div>
        <div className={styles.content}>{children}</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add customer icon styling**

Modify `frontend/src/components/DashboardLayout.module.css` by adding this block after `.roleIconAdmin`:

```css
.roleIconCustomer {
  background: hsla(199, 89%, 48%, 0.15);
}
```

- [ ] **Step 4: Create the account route guard and shell**

Create `frontend/src/app/account/layout.tsx`:

```tsx
"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { useAuth } from "@/lib/AuthContext";
import type { UserRole } from "@/types";

const CUSTOMER_NAV = [
  { href: "/account/settings", label: "Settings", icon: "⚙️" },
];

function redirectForRole(role: UserRole): string {
  if (role === "admin") return "/admin";
  if (role === "seller") return "/seller";
  return "/";
}

export default function AccountLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { dbUser, loading } = useAuth();

  useEffect(() => {
    if (loading) return;
    if (!dbUser) {
      router.replace("/login");
      return;
    }
    if (dbUser.role !== "customer") {
      router.replace(redirectForRole(dbUser.role));
    }
  }, [loading, dbUser, router]);

  if (loading || !dbUser || dbUser.role !== "customer") {
    return (
      <div style={{ padding: "4rem", textAlign: "center", color: "var(--color-neutral-500)" }}>
        Loading…
      </div>
    );
  }

  const title = pathname === "/account/settings" ? "Account settings" : "Account";
  const roleName = dbUser.full_name || dbUser.email;

  return (
    <DashboardLayout
      role="customer"
      roleName={roleName}
      title={title}
      navItems={CUSTOMER_NAV}
    >
      {children}
    </DashboardLayout>
  );
}
```

- [ ] **Step 5: Redirect `/account` to `/account/settings`**

Create `frontend/src/app/account/page.tsx`:

```tsx
import { redirect } from "next/navigation";

export default function AccountPage() {
  redirect("/account/settings");
}
```

- [ ] **Step 6: Run frontend type/lint check**

Run: `cd frontend && npm run lint`

Expected: PASS with no ESLint errors.

- [ ] **Step 7: Commit the account shell**

```bash
git add frontend/src/types/index.ts frontend/src/components/DashboardLayout.tsx frontend/src/components/DashboardLayout.module.css frontend/src/app/account/layout.tsx frontend/src/app/account/page.tsx
git commit -m "feat(account): add customer account shell"
```

---

## Task 4: Frontend settings page

**Files:**
- Create: `frontend/src/app/account/settings/page.tsx`
- Create: `frontend/src/app/account/settings/page.module.css`
- Test: frontend lint/build

- [ ] **Step 1: Create the customer settings page**

Create `frontend/src/app/account/settings/page.tsx`:

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { AddressFields, emptyAddress } from "@/components/AddressFields";
import { del, get, patch, post, put } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { formatAddress } from "@/lib/format-address";
import type { AddressFieldsErrors } from "@/components/AddressFields";
import type { Address, CustomerAddress, CustomerProfile } from "@/types";
import styles from "./page.module.css";

interface ProfileForm {
  first_name: string;
  last_name: string;
  phone: string;
}

interface ProfileErrors {
  first_name?: string;
  last_name?: string;
  phone?: string;
}

interface AddressForm {
  id: number | null;
  label: string;
  is_default: boolean;
  address: Address;
}

interface FastApiValidationIssue {
  loc?: Array<string | number>;
  msg?: string;
}

const PHONE_RE = /^[0-9+() -]{7,20}$/;

function profileFormFrom(profile: CustomerProfile): ProfileForm {
  return {
    first_name: profile.first_name,
    last_name: profile.last_name ?? "",
    phone: profile.phone ?? "",
  };
}

function blankAddressForm(): AddressForm {
  return {
    id: null,
    label: "",
    is_default: false,
    address: emptyAddress(),
  };
}

function addressFormFrom(customerAddress: CustomerAddress): AddressForm {
  return {
    id: customerAddress.id,
    label: customerAddress.label ?? "",
    is_default: customerAddress.is_default,
    address: customerAddress.address,
  };
}

function apiErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as FastApiValidationIssue;
    if (typeof first.msg === "string") return first.msg;
  }
  if (error instanceof Error) return error.message;
  return fallback;
}

function validationErrorsForPrefix(
  error: unknown,
  prefix: string
): Record<string, string> {
  const detail = (error as { detail?: unknown })?.detail;
  if (!Array.isArray(detail)) return {};

  return detail.reduce<Record<string, string>>((acc, issue: FastApiValidationIssue) => {
    if (!Array.isArray(issue.loc) || typeof issue.msg !== "string") return acc;
    const prefixIndex = issue.loc.indexOf(prefix);
    if (prefixIndex === -1) return acc;
    const field = issue.loc[prefixIndex + 1];
    if (typeof field === "string") acc[field] = issue.msg;
    return acc;
  }, {});
}

function normalizeOptional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export default function AccountSettingsPage() {
  const { token } = useAuth();
  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [profileForm, setProfileForm] = useState<ProfileForm>({
    first_name: "",
    last_name: "",
    phone: "",
  });
  const [profileErrors, setProfileErrors] = useState<ProfileErrors>({});
  const [addressForm, setAddressForm] = useState<AddressForm | null>(null);
  const [addressErrors, setAddressErrors] = useState<AddressFieldsErrors>({});
  const [sectionError, setSectionError] = useState<string | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);
  const [savingAddress, setSavingAddress] = useState(false);
  const [busyAddressId, setBusyAddressId] = useState<number | null>(null);

  useEffect(() => {
    if (!token) return;
    let active = true;
    setLoadingProfile(true);
    get<CustomerProfile>("/api/v1/customers/me", token)
      .then((data) => {
        if (!active) return;
        setProfile(data);
        setProfileForm(profileFormFrom(data));
      })
      .catch((error) => {
        if (!active) return;
        setSectionError(apiErrorMessage(error, "Could not load account settings."));
      })
      .finally(() => {
        if (active) setLoadingProfile(false);
      });

    return () => {
      active = false;
    };
  }, [token]);

  const sortedAddresses = useMemo(() => {
    if (!profile) return [];
    return [...profile.addresses].sort((a, b) => {
      if (a.is_default === b.is_default) return a.id - b.id;
      return a.is_default ? -1 : 1;
    });
  }, [profile]);

  const validateProfile = (): ProfileErrors => {
    const errors: ProfileErrors = {};
    if (!profileForm.first_name.trim()) {
      errors.first_name = "First name is required.";
    }
    if (profileForm.phone.trim() && !PHONE_RE.test(profileForm.phone.trim())) {
      errors.phone = "Use 7-20 digits, spaces, +, -, or parentheses.";
    }
    return errors;
  };

  const saveProfile = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token) return;
    setSectionError(null);
    const errors = validateProfile();
    setProfileErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSavingProfile(true);
    try {
      const next = await patch<CustomerProfile>(
        "/api/v1/customers/me",
        {
          first_name: profileForm.first_name.trim(),
          last_name: normalizeOptional(profileForm.last_name),
          phone: normalizeOptional(profileForm.phone),
        },
        token
      );
      setProfile(next);
      setProfileForm(profileFormFrom(next));
      setProfileErrors({});
    } catch (error) {
      setProfileErrors(validationErrorsForPrefix(error, "body") as ProfileErrors);
      setSectionError(apiErrorMessage(error, "Could not save profile changes."));
    } finally {
      setSavingProfile(false);
    }
  };

  const openNewAddressForm = () => {
    setAddressErrors({});
    setSectionError(null);
    setAddressForm(blankAddressForm());
  };

  const editAddress = (customerAddress: CustomerAddress) => {
    setAddressErrors({});
    setSectionError(null);
    setAddressForm(addressFormFrom(customerAddress));
  };

  const saveAddress = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token || !addressForm) return;
    setSectionError(null);
    setAddressErrors({});
    setSavingAddress(true);

    const payload = {
      label: normalizeOptional(addressForm.label),
      is_default: addressForm.is_default,
      address: addressForm.address,
    };

    try {
      const next =
        addressForm.id === null
          ? await post<CustomerProfile>("/api/v1/customers/me/addresses", payload, token)
          : await put<CustomerProfile>(
              `/api/v1/customers/me/addresses/${addressForm.id}`,
              payload,
              token
            );
      setProfile(next);
      setAddressForm(null);
      setAddressErrors({});
    } catch (error) {
      setAddressErrors(validationErrorsForPrefix(error, "address") as AddressFieldsErrors);
      setSectionError(apiErrorMessage(error, "Could not save delivery address."));
    } finally {
      setSavingAddress(false);
    }
  };

  const setDefaultAddress = async (customerAddress: CustomerAddress) => {
    if (!token || customerAddress.is_default) return;
    setSectionError(null);
    setBusyAddressId(customerAddress.id);
    try {
      const next = await post<CustomerProfile>(
        `/api/v1/customers/me/addresses/${customerAddress.id}/default`,
        undefined,
        token
      );
      setProfile(next);
    } catch (error) {
      setSectionError(apiErrorMessage(error, "Could not set default address."));
    } finally {
      setBusyAddressId(null);
    }
  };

  const deleteAddress = async (customerAddress: CustomerAddress) => {
    if (!token) return;
    const label = customerAddress.label || "this address";
    if (!window.confirm(`Delete ${label}?`)) return;

    setSectionError(null);
    setBusyAddressId(customerAddress.id);
    try {
      const next = await del<CustomerProfile>(
        `/api/v1/customers/me/addresses/${customerAddress.id}`,
        token
      );
      setProfile(next);
      if (addressForm?.id === customerAddress.id) setAddressForm(null);
    } catch (error) {
      setSectionError(apiErrorMessage(error, "Could not delete address."));
    } finally {
      setBusyAddressId(null);
    }
  };

  if (loadingProfile) {
    return <div className={styles.loading}>Loading account settings…</div>;
  }

  if (!profile) {
    return (
      <div className={styles.panel}>
        <div className={styles.errorBanner}>
          {sectionError ?? "Could not load account settings."}
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      {sectionError && <div className={styles.errorBanner}>{sectionError}</div>}

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <h2 className={styles.sectionTitle}>Profile</h2>
            <p className={styles.sectionSubtitle}>{profile.email}</p>
          </div>
        </div>

        <form className={styles.profileForm} onSubmit={saveProfile}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="first-name">First name</label>
            <input
              id="first-name"
              className={`${styles.input} ${profileErrors.first_name ? styles.inputError : ""}`}
              value={profileForm.first_name}
              onChange={(event) =>
                setProfileForm((current) => ({ ...current, first_name: event.target.value }))
              }
              maxLength={80}
              required
            />
            {profileErrors.first_name && (
              <span className={styles.errorText}>{profileErrors.first_name}</span>
            )}
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="last-name">Last name</label>
            <input
              id="last-name"
              className={`${styles.input} ${profileErrors.last_name ? styles.inputError : ""}`}
              value={profileForm.last_name}
              onChange={(event) =>
                setProfileForm((current) => ({ ...current, last_name: event.target.value }))
              }
              maxLength={80}
            />
            {profileErrors.last_name && (
              <span className={styles.errorText}>{profileErrors.last_name}</span>
            )}
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="phone">Phone</label>
            <input
              id="phone"
              className={`${styles.input} ${profileErrors.phone ? styles.inputError : ""}`}
              value={profileForm.phone}
              onChange={(event) =>
                setProfileForm((current) => ({ ...current, phone: event.target.value }))
              }
              inputMode="tel"
              maxLength={20}
            />
            {profileErrors.phone && (
              <span className={styles.errorText}>{profileErrors.phone}</span>
            )}
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="email">Email</label>
            <input
              id="email"
              className={styles.input}
              value={profile.email}
              readOnly
              disabled
            />
          </div>

          <div className={styles.formActions}>
            <button className="btn btn-primary" type="submit" disabled={savingProfile}>
              {savingProfile ? "Saving…" : "Save profile"}
            </button>
          </div>
        </form>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <h2 className={styles.sectionTitle}>Saved delivery addresses</h2>
            <p className={styles.sectionSubtitle}>
              {sortedAddresses.length} saved address{sortedAddresses.length === 1 ? "" : "es"}
            </p>
          </div>
          <button className="btn btn-outline" type="button" onClick={openNewAddressForm}>
            Add address
          </button>
        </div>

        {sortedAddresses.length === 0 && (
          <div className={styles.emptyState}>
            <p>No delivery addresses are saved.</p>
            <button className="btn btn-primary" type="button" onClick={openNewAddressForm}>
              Add address
            </button>
          </div>
        )}

        {sortedAddresses.length > 0 && (
          <div className={styles.addressGrid}>
            {sortedAddresses.map((customerAddress) => (
              <article className={styles.addressCard} key={customerAddress.id}>
                <div className={styles.addressCardHeader}>
                  <div>
                    <h3 className={styles.addressLabel}>
                      {customerAddress.label || "Address"}
                    </h3>
                    {customerAddress.is_default && (
                      <span className={styles.defaultBadge}>Default</span>
                    )}
                  </div>
                </div>
                <p className={styles.addressText}>{formatAddress(customerAddress.address)}</p>
                <div className={styles.addressActions}>
                  <button
                    className={styles.textButton}
                    type="button"
                    onClick={() => editAddress(customerAddress)}
                    disabled={busyAddressId === customerAddress.id}
                  >
                    Edit
                  </button>
                  <button
                    className={styles.textButton}
                    type="button"
                    onClick={() => setDefaultAddress(customerAddress)}
                    disabled={customerAddress.is_default || busyAddressId === customerAddress.id}
                  >
                    Set default
                  </button>
                  <button
                    className={`${styles.textButton} ${styles.dangerButton}`}
                    type="button"
                    onClick={() => deleteAddress(customerAddress)}
                    disabled={busyAddressId === customerAddress.id}
                  >
                    Delete
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}

        {addressForm && (
          <form className={styles.addressForm} onSubmit={saveAddress}>
            <div className={styles.addressFormHeader}>
              <h3 className={styles.addressFormTitle}>
                {addressForm.id === null ? "Add delivery address" : "Edit delivery address"}
              </h3>
              <button
                className={styles.textButton}
                type="button"
                onClick={() => setAddressForm(null)}
                disabled={savingAddress}
              >
                Cancel
              </button>
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="address-label">Label</label>
              <input
                id="address-label"
                className={styles.input}
                value={addressForm.label}
                onChange={(event) =>
                  setAddressForm((current) =>
                    current ? { ...current, label: event.target.value } : current
                  )
                }
                placeholder="Home, Work, Family"
                maxLength={60}
                disabled={savingAddress}
              />
            </div>

            <AddressFields
              value={addressForm.address}
              onChange={(address) =>
                setAddressForm((current) => (current ? { ...current, address } : current))
              }
              errors={addressErrors}
              disabled={savingAddress}
            />

            <label className={styles.checkboxRow}>
              <input
                type="checkbox"
                checked={addressForm.is_default}
                onChange={(event) =>
                  setAddressForm((current) =>
                    current ? { ...current, is_default: event.target.checked } : current
                  )
                }
                disabled={savingAddress}
              />
              Make this the default delivery address
            </label>

            <div className={styles.formActions}>
              <button className="btn btn-primary" type="submit" disabled={savingAddress}>
                {savingAddress ? "Saving…" : "Save address"}
              </button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Create the customer settings styles**

Create `frontend/src/app/account/settings/page.module.css`:

```css
.page {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  max-width: var(--container-lg);
}

.loading {
  color: var(--color-neutral-500);
  padding: var(--space-8);
  text-align: center;
}

.section,
.panel {
  background: var(--color-neutral-0);
  border: 1px solid var(--color-neutral-100);
  border-radius: var(--radius-md);
  padding: var(--space-5);
}

.sectionHeader {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

.sectionTitle {
  font-size: var(--font-xl);
  font-weight: var(--weight-semibold);
  color: var(--color-neutral-900);
}

.sectionSubtitle {
  font-size: var(--font-sm);
  color: var(--color-neutral-500);
  margin-top: var(--space-1);
}

.profileForm {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-4);
}

@media (min-width: 700px) {
  .profileForm {
    grid-template-columns: 1fr 1fr;
  }
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1-5);
}

.label {
  font-size: var(--font-sm);
  font-weight: var(--weight-medium);
  color: var(--color-neutral-700);
}

.input {
  width: 100%;
  border: 1.5px solid var(--color-neutral-200);
  border-radius: var(--radius-md);
  background: var(--color-neutral-0);
  color: var(--color-neutral-800);
  font: inherit;
  padding: var(--space-3) var(--space-4);
  outline: none;
  transition: all var(--duration-fast) var(--ease-default);
}

.input:focus {
  border-color: var(--color-primary-400);
  box-shadow: 0 0 0 3px hsla(18, 90%, 52%, 0.12);
}

.input:disabled {
  background: var(--color-neutral-100);
  color: var(--color-neutral-500);
  cursor: not-allowed;
}

.inputError {
  border-color: var(--color-error);
}

.errorText {
  color: var(--color-error);
  font-size: var(--font-xs);
}

.errorBanner {
  background: hsla(0, 84%, 60%, 0.1);
  border: 1px solid hsla(0, 84%, 60%, 0.25);
  border-radius: var(--radius-md);
  color: var(--color-error);
  font-size: var(--font-sm);
  padding: var(--space-3) var(--space-4);
}

.formActions {
  display: flex;
  justify-content: flex-start;
  grid-column: 1 / -1;
  margin-top: var(--space-2);
}

.addressGrid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-4);
}

@media (min-width: 720px) {
  .addressGrid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.addressCard {
  border: 1px solid var(--color-neutral-100);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.addressCardHeader {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.addressLabel {
  font-size: var(--font-base);
  font-weight: var(--weight-semibold);
  color: var(--color-neutral-900);
}

.defaultBadge {
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-full);
  background: var(--color-accent-50);
  color: var(--color-accent-700);
  font-size: var(--font-xs);
  font-weight: var(--weight-semibold);
  margin-top: var(--space-2);
  padding: var(--space-1) var(--space-2);
}

.addressText {
  color: var(--color-neutral-600);
  font-size: var(--font-sm);
}

.addressActions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-top: auto;
}

.textButton {
  color: var(--color-primary-600);
  font-size: var(--font-sm);
  font-weight: var(--weight-semibold);
}

.textButton:hover:not(:disabled) {
  color: var(--color-primary-700);
}

.textButton:disabled {
  color: var(--color-neutral-400);
  cursor: not-allowed;
}

.dangerButton {
  color: var(--color-error);
}

.emptyState {
  align-items: flex-start;
  border: 1px dashed var(--color-neutral-200);
  border-radius: var(--radius-md);
  color: var(--color-neutral-500);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-5);
}

.addressForm {
  border-top: 1px solid var(--color-neutral-100);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  margin-top: var(--space-5);
  padding-top: var(--space-5);
}

.addressFormHeader {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: var(--space-4);
}

.addressFormTitle {
  color: var(--color-neutral-900);
  font-size: var(--font-lg);
  font-weight: var(--weight-semibold);
}

.checkboxRow {
  align-items: center;
  color: var(--color-neutral-700);
  display: flex;
  font-size: var(--font-sm);
  gap: var(--space-2);
}

@media (max-width: 640px) {
  .section,
  .panel {
    padding: var(--space-4);
  }

  .sectionHeader {
    align-items: stretch;
    flex-direction: column;
  }
}
```

- [ ] **Step 3: Run frontend lint**

Run: `cd frontend && npm run lint`

Expected: PASS with no ESLint errors.

- [ ] **Step 4: Run frontend production build**

Run: `cd frontend && npm run build`

Expected: PASS and the build completes successfully.

- [ ] **Step 5: Commit the settings page**

```bash
git add frontend/src/app/account/settings/page.tsx frontend/src/app/account/settings/page.module.css
git commit -m "feat(account): add customer settings page"
```

---

## Task 5: End-to-end verification

**Files:**
- Verify only; no file changes expected.

- [ ] **Step 1: Run backend customer and regression tests**

Run: `cd backend/app && uv run pytest tests/test_customers.py tests/test_auth.py tests/test_stores.py -v`

Expected: all selected tests pass.

- [ ] **Step 2: Run backend lint**

Run: `cd backend/app && uv run ruff check .`

Expected: PASS with no lint errors.

- [ ] **Step 3: Run frontend lint**

Run: `cd frontend && npm run lint`

Expected: PASS with no ESLint errors.

- [ ] **Step 4: Run frontend build**

Run: `cd frontend && npm run build`

Expected: PASS and the Next.js production build completes.

- [ ] **Step 5: Manual route and role checks**

Start infrastructure and app servers:

```bash
docker-compose up -d
cd backend/app && uv run alembic upgrade head && uv run uvicorn app.main:app --reload
cd frontend && npm run dev
```

Manual checks:

- Visit `http://localhost:3000/account` as a signed-in customer and confirm the browser lands on `/account/settings`.
- Edit first name, last name, and phone; confirm the values remain after a refresh.
- Add a delivery address with label `Home`; confirm the card appears with formatted address text.
- Edit the address label to `Family`; confirm the card updates.
- Set the address as default; confirm the default badge appears.
- Add a second address with `is_default` checked; confirm the previous address loses its default badge.
- Delete the default address; confirm no remaining address has a default badge.
- Visit `/account/settings` while signed out; confirm redirect to `/login`.
- Visit `/account/settings` as a seller; confirm redirect to `/seller`.
- Visit `/account/settings` as an admin; confirm redirect to `/admin`.

- [ ] **Step 6: Commit verification notes only if files changed**

If no files changed during verification, do not create a commit. If a small fix was required, commit only the changed files:

```bash
git add <changed-files>
git commit -m "fix(account): address verification issue"
```

---

## Rollout Notes

- No database migration.
- No environment variable changes.
- No feature flag.
- Checkout address selection remains out of scope and can consume `GET /api/v1/customers/me` later.
