import logging
import time
from typing import Any

from app.core.celery_app import celery_app


@celery_app.task(name="test_celery_task", bind=True)  # type: ignore[untyped-decorator]
def test_celery_task(self: Any, word: str) -> str:
    time.sleep(2)
    return f"Celery processed the word: {word}"


@celery_app.task(name="send_otp_email_async")  # type: ignore[untyped-decorator]
def send_otp_email_async(to: str, code: str) -> None:
    """Send an OTP code email via the configured provider (sync wrapper for Celery)."""
    from app.core.config import settings

    if settings.EMAIL_PROVIDER == "resend":
        import httpx
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": settings.RESEND_FROM_EMAIL,
                "to": [to],
                "subject": "Your Khana Bazaar login code",
                "text": f"Your one-time login code is: {code}\n\nExpires in 10 minutes.",
            },
            timeout=10,
        )
        resp.raise_for_status()
    else:
        logging.getLogger(__name__).info("EMAIL to=%s code=%s", to, code)


def _resolve_email(to: str, subject: str, body: str) -> None:
    """Send an email via the configured provider, mirroring the OTP email pattern."""
    from app.core.config import settings

    if settings.EMAIL_PROVIDER == "resend":
        import httpx
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": settings.RESEND_FROM_EMAIL,
                "to": [to],
                "subject": subject,
                "text": body,
            },
            timeout=10,
        )
        resp.raise_for_status()
    else:
        logging.getLogger(__name__).info(
            "EMAIL to=%s subject=%s body=%s", to, subject, body
        )


def _load_order_email_context(order_id: int) -> dict[str, Any]:
    """Load order/store/seller_user/customer_user scalars for email composition.

    Opens an isolated event loop because Celery's prefork worker doesn't have an
    asyncio loop and pytest's anyio loop would conflict if reused. Returns an
    empty dict if the order cannot be found (callers should short-circuit).
    """
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.core.config import settings
    from app.models.base import User
    from app.models.commerce import Order
    from app.models.profile import CustomerProfile, SellerProfile
    from app.models.store import Store

    async def _load() -> dict[str, Any]:
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        try:
            async with AsyncSession(engine) as session:
                order = (
                    await session.exec(select(Order).where(Order.id == order_id))
                ).first()
                if order is None:
                    return {}
                store = (
                    await session.exec(select(Store).where(Store.id == order.store_id))
                ).first()
                seller_user = None
                if store is not None:
                    seller_profile = (
                        await session.exec(
                            select(SellerProfile).where(
                                SellerProfile.id == store.seller_profile_id
                            )
                        )
                    ).first()
                    if seller_profile is not None:
                        seller_user = (
                            await session.exec(
                                select(User).where(User.id == seller_profile.user_id)
                            )
                        ).first()
                customer_profile = (
                    await session.exec(
                        select(CustomerProfile).where(
                            CustomerProfile.id == order.customer_profile_id
                        )
                    )
                ).first()
                customer_user = None
                if customer_profile is not None:
                    customer_user = (
                        await session.exec(
                            select(User).where(User.id == customer_profile.user_id)
                        )
                    ).first()
                return {
                    "order_id": order.id,
                    "order_total": order.total,
                    "order_status": order.status.value if hasattr(order.status, "value") else str(order.status),
                    "store_name": store.name if store is not None else None,
                    "seller_email": seller_user.email if seller_user is not None else None,
                    "customer_email": customer_user.email if customer_user is not None else None,
                }
        finally:
            await engine.dispose()

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_load())
    finally:
        loop.close()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_order_placed_seller_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_order_placed_seller_async(order_id: int) -> None:
    """Notify the seller that a new order was placed at their store."""
    ctx = _load_order_email_context(order_id)
    if not ctx or not ctx.get("seller_email"):
        return
    subject = f"New order received at {ctx.get('store_name') or 'your store'}"
    body = (
        f"You have a new order #{ctx['order_id']} for "
        f"{ctx.get('store_name') or 'your store'}.\n"
        f"Order total: {ctx['order_total']}.\n"
        f"Please prepare it for packing."
    )
    _resolve_email(ctx["seller_email"], subject, body)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_order_confirmed_customer_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_order_confirmed_customer_async(order_ids: list[int]) -> None:
    """Notify the customer that their order(s) were confirmed.

    Accepts a list of order ids (a single checkout may produce multiple
    per-store orders). Uses the customer email from the first resolvable order.
    """
    customer_email: str | None = None
    parts: list[str] = []
    for oid in order_ids:
        ctx = _load_order_email_context(oid)
        if not ctx:
            continue
        if customer_email is None and ctx.get("customer_email"):
            customer_email = ctx["customer_email"]
        parts.append(
            f"Order #{ctx['order_id']} from {ctx.get('store_name') or 'a store'} "
            f"- total {ctx['order_total']}"
        )
    if not customer_email or not parts:
        return
    subject = "Your Khana Bazaar order is confirmed"
    body = "Thanks for shopping with Khana Bazaar!\n\n" + "\n".join(parts)
    _resolve_email(customer_email, subject, body)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_order_status_changed_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_order_status_changed_async(
    order_id: int, new_status: str, recipient: str = "customer"
) -> None:
    """Notify the customer or seller that an order status changed."""
    ctx = _load_order_email_context(order_id)
    if not ctx:
        return
    if recipient == "seller":
        to = ctx.get("seller_email")
    else:
        to = ctx.get("customer_email")
    if not to:
        return
    subject = f"Order #{ctx['order_id']} status: {new_status}"
    body = (
        f"Order #{ctx['order_id']} from "
        f"{ctx.get('store_name') or 'a store'} is now '{new_status}'."
    )
    _resolve_email(to, subject, body)
