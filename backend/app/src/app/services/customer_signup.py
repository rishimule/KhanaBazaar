# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Rules the two customer-signup paths share (spec 2026-10-08).

`POST /auth/otp/verify` (new email) and `POST /referrals/accept` both create a
customer, and both must carry a phone the server has accepted under the same
uniqueness rule. Keeping the rules here stops the two paths drifting apart.
"""
from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.security import decode_customer_signup_phone_token
from app.models.base import User
from app.models.profile import CustomerProfile

_GMAIL_DOMAINS = frozenset({"gmail.com", "googlemail.com"})


async def customer_phone_taken(session: AsyncSession, phone: str) -> bool:
    """Whether a customer profile already holds `phone`.

    Customer scope only, matching ix_customerprofile_phone and the profile
    phone flow: a number on a seller or admin profile may also sit on a
    customer one. A deleted, suspended or deactivated customer still holds
    their number, because accounts are never scrubbed."""
    row = (
        await session.exec(
            select(CustomerProfile.id).where(CustomerProfile.phone == phone)
        )
    ).first()
    return row is not None


async def email_registered(session: AsyncSession, email: str) -> bool:
    row = (await session.exec(select(User.id).where(User.email == email))).first()
    return row is not None


def require_signup_phone(phone_token: str | None, email: str) -> str:
    """The phone a new customer account must carry, read from its token.

    `email` must already be normalized. Raises 400 phone_required (no
    token), 410 phone_token_expired, or 400 invalid_phone_token: a bad token,
    one minted for a different email, or one that took the number on trust
    while PHONE_OTP_ENABLED is now on. The clients answer that last case like
    any unusable token — "confirm your number again" — and the re-request
    then sends a real code, so nothing created after the cutover carries an
    unproven "verified" number."""
    if not phone_token:
        raise HTTPException(status_code=400, detail={"error": "phone_required"})
    token_email, phone, proven = decode_customer_signup_phone_token(phone_token)
    if token_email != email or (settings.PHONE_OTP_ENABLED and not proven):
        raise HTTPException(status_code=400, detail={"error": "invalid_phone_token"})
    return phone


def budget_identity(email: str) -> str:
    """`email` folded for rate budgets only — never for identity. A `+tag` is
    dropped everywhere, and Gmail's ignored dots are removed, so trivial
    variants of one inbox share one budget."""
    local, sep, domain = email.strip().lower().rpartition("@")
    if not sep:
        return email.strip().lower()
    local = local.split("+", 1)[0]
    if domain in _GMAIL_DOMAINS:
        local = local.replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"
