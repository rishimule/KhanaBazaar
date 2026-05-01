from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
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
        .order_by(desc(CustomerAddress.is_default), CustomerAddress.id)  # type: ignore[arg-type]
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
    cleared = False
    for customer_address in addresses:
        if customer_address.is_default:
            customer_address.is_default = False
            session.add(customer_address)
            cleared = True
    if cleared:
        await session.flush()


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
        assert profile.id is not None
        await _clear_default_addresses(session, profile.id)

    customer_address.label = body.label
    customer_address.is_default = body.is_default
    for key, value in address_from_payload(body.address).items():
        setattr(customer_address.address, key, value)

    session.add(customer_address.address)
    session.add(customer_address)
    await session.commit()
    await session.refresh(profile)
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
    assert profile.id is not None

    await _clear_default_addresses(session, profile.id)
    customer_address.is_default = True
    session.add(customer_address)
    await session.commit()
    await session.refresh(profile)
    return await _profile_response(session, current_user, profile)
