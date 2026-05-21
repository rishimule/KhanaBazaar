# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import logging
import time
from typing import Any, Literal

# Ensure search tasks are discovered by the worker.
import app.search.tasks  # noqa: F401
from app.core.celery_app import celery_app


@celery_app.task(name="test_celery_task", bind=True)  # type: ignore[untyped-decorator]
def test_celery_task(self: Any, word: str) -> str:
    time.sleep(2)
    return f"Celery processed the word: {word}"


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_otp_email_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_otp_email_async(to: str, code: str) -> None:
    """Render the otp_login template and dispatch.

    This task is the fallback path when the inline send in `/auth/otp/request`
    raises an `httpx.HTTPError` (Resend timeout / 5xx / network).
    """
    from app.core.config import settings
    from app.core.email_render import render_email

    payload = render_email(
        "otp_login",
        {"code": code, "ttl_minutes": settings.OTP_TTL_SECONDS // 60},
        lang="en",
    )
    _resolve_email(
        to,
        payload.subject,
        payload.text,
        html=payload.html,
        reply_to=settings.EMAIL_REPLY_TO,
    )


@celery_app.task(name="send_support_email")  # type: ignore[untyped-decorator]
def send_support_email(customer_email: str, subject: str, message: str) -> None:
    """Forward a customer support message to the configured SUPPORT_EMAIL inbox."""
    from app.core.config import settings

    _resolve_email(
        settings.SUPPORT_EMAIL,
        f"[Support] {subject}",
        f"From: {customer_email}\n\n{message}",
    )


def _resolve_email(
    to: str,
    subject: str,
    body: str,
    *,
    html: str | None = None,
    reply_to: str | None = None,
) -> None:
    """Send an email via the configured provider, mirroring the OTP email pattern."""
    from app.core.config import settings

    if settings.EMAIL_PROVIDER == "resend":
        import httpx

        payload: dict[str, object] = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "text": body,
        }
        if html is not None:
            payload["html"] = html
        if reply_to is not None:
            payload["reply_to"] = reply_to
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
    else:
        logging.getLogger(__name__).info(
            "EMAIL to=%s subject=%s body=%s", to, subject, body
        )


def _load_order_email_context(order_id: int) -> dict[str, Any]:
    """Load order/store/seller_user/customer_user scalars for email composition.

    Always runs the async loader in a worker thread with its own event loop.
    This works under Celery's prefork worker (no ambient loop) AND in EAGER
    test mode where the caller is already inside pytest-anyio's loop — a
    second `loop.run_until_complete()` on the calling thread would raise
    "Cannot run the event loop while another loop is running."

    Returns an empty dict if the order cannot be found (callers short-circuit).
    """
    import asyncio
    import concurrent.futures

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.core.config import settings
    from app.models.base import User
    from app.models.commerce import Order
    from app.models.profile import CustomerProfile, SellerProfile
    from app.models.store import Store

    async def _load() -> dict[str, Any]:
        from app.models.commerce import OrderItem

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
                items_rows = (
                    await session.exec(
                        select(OrderItem).where(OrderItem.order_id == order_id)
                    )
                ).all()
                items = [
                    {
                        "name": row.product_name_snapshot,
                        "qty": row.quantity,
                        "unit_price": row.unit_price_snapshot,
                        "line_total": row.line_total,
                    }
                    for row in items_rows
                ]
                return {
                    "order_id": order.id,
                    "order_total": order.total,
                    "order_status": order.status.value,
                    "service_name": order.service_name_snapshot,
                    "store_name": store.name if store is not None else None,
                    "seller_email": seller_user.email if seller_user is not None else None,
                    "customer_email": customer_user.email if customer_user is not None else None,
                    "items": items,
                    "customer_first_name": (
                        customer_profile.first_name if customer_profile else None
                    ),
                    "customer_lang": (
                        customer_user.preferred_language if customer_user else "en"
                    ),
                    "seller_lang": (
                        seller_user.preferred_language if seller_user else "en"
                    ),
                    "delivery_address_snapshot": order.delivery_address_snapshot,
                }
        finally:
            await engine.dispose()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(_load())).result()


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
    subject = (
        f"New {ctx['service_name']} order received at "
        f"{ctx.get('store_name') or 'your store'}"
    )
    body = (
        f"You have a new {ctx['service_name']} order #{ctx['order_id']} for "
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
            f"Order #{ctx['order_id']} · {ctx['service_name']} "
            f"from {ctx.get('store_name') or 'a store'} - total {ctx['order_total']}"
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
    order_id: int, new_status: str, recipient: Literal["customer", "seller"] = "customer"
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
    subject = (
        f"Order #{ctx['order_id']} · {ctx['service_name']} status: {new_status}"
    )
    body = (
        f"Order #{ctx['order_id']} ({ctx['service_name']}) from "
        f"{ctx.get('store_name') or 'a store'} is now '{new_status}'."
    )
    _resolve_email(to, subject, body)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_admin_order_action_email",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_admin_order_action_email(
    order_id: int, action: str, reason: str
) -> None:
    """Notify the seller that an admin took action on one of their orders."""
    ctx = _load_order_email_context(order_id)
    if not ctx or not ctx.get("seller_email"):
        return
    subject = f"Admin updated your order #{ctx['order_id']}"
    body = (
        f"Hi,\n\nAn admin updated your order #{ctx['order_id']} "
        f"({ctx['service_name']}) at {ctx.get('store_name') or 'your store'}.\n"
        f"Action: {action}\n"
        f"Reason: {reason or '(none provided)'}\n\n"
        "If you have questions, reply to this email."
    )
    _resolve_email(ctx["seller_email"], subject, body)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_seller_approved_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_seller_approved_async(to_email: str, business_name: str) -> None:
    """Notify a seller that their application has been approved."""
    if not to_email:
        return
    subject = "Your Khana Bazaar seller application is approved"
    body = (
        f"Congratulations! Your seller application for {business_name} has been approved.\n\n"
        "Sign in to your seller dashboard to start managing your store inventory and accepting orders."
    )
    _resolve_email(to_email, subject, body)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_seller_rejected_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_seller_rejected_async(
    to_email: str, business_name: str, reason: str
) -> None:
    """Notify a seller that their application has been rejected."""
    if not to_email:
        return
    subject = "Update on your Khana Bazaar seller application"
    body = (
        f"Your seller application for {business_name} was not approved at this time.\n\n"
        f"Reason: {reason}\n\n"
        "You may update your application details and resubmit for review."
    )
    _resolve_email(to_email, subject, body)


# ---------------------------------------------------------------------------
# Geo backfill — one-shot Celery task to forward-geocode legacy store/business
# addresses missing lat/lng. Customer addresses NOT touched (saves Google
# quota; they re-fill lazily on next user-driven address edit).
# ---------------------------------------------------------------------------


async def _forward_geocode_one(query: str) -> tuple[float, float] | None:
    from app.core.config import settings
    from app.core.google_maps import GoogleMapsClient, GoogleMapsError

    if not settings.GOOGLE_MAPS_SERVER_API_KEY:
        return None
    client = GoogleMapsClient(api_key=settings.GOOGLE_MAPS_SERVER_API_KEY)
    try:
        body = await client.get(
            "/geocode/json", {"address": query, "components": "country:IN"}
        )
        results = body.get("results", [])
        if not results or results[0].get("partial_match", False):
            return None
        loc = results[0]["geometry"]["location"]
        return float(loc["lat"]), float(loc["lng"])
    except GoogleMapsError:
        return None
    finally:
        await client.aclose()


async def _run_backfill() -> dict[str, int]:
    """Forward-geocode rows of `address` reachable via Store or
    SellerProfile.business_address that lack lat/lng. Idempotent."""
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.core.config import settings
    from app.utils.digipin import encode as digipin_encode

    sql_select = text(
        "SELECT a.id, a.address_line1, a.city, a.state, a.pincode "
        "FROM address a "
        "WHERE a.latitude IS NULL "
        "  AND ("
        "    EXISTS (SELECT 1 FROM store s WHERE s.address_id = a.id) "
        "    OR EXISTS ("
        "      SELECT 1 FROM sellerprofile sp WHERE sp.business_address_id = a.id"
        "    )"
        "  )"
    )
    sql_update = text(
        "UPDATE address SET latitude = :lat, longitude = :lng, "
        "  digipin = :digipin, location_source = 'geocoded' "
        "WHERE id = :id"
    )

    filled = 0
    skipped = 0
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    try:
        async with AsyncSession(engine) as session:
            rows = (await session.exec(sql_select)).all()  # type: ignore[call-overload]
            for row in rows:
                query = (
                    f"{row.address_line1}, {row.city}, {row.state} {row.pincode}, India"
                )
                coords = await _forward_geocode_one(query)
                if coords is None:
                    skipped += 1
                    continue
                lat, lng = coords
                try:
                    digipin = digipin_encode(lat, lng)
                except ValueError:
                    digipin = None
                await session.exec(  # type: ignore[call-overload]
                    sql_update.bindparams(id=row.id, lat=lat, lng=lng, digipin=digipin)
                )
                filled += 1
                await asyncio.sleep(0.1)  # 10 req/s ceiling
            await session.commit()
    finally:
        await engine.dispose()
    return {"filled": filled, "skipped": skipped}


@celery_app.task(name="geo.backfill_store_addresses")  # type: ignore[untyped-decorator]
def backfill_store_addresses_geocode() -> dict[str, int]:
    """Forward-geocode addresses linked to Store or SellerProfile.business_address.

    Skips addresses that already have lat/lng AND customer-only addresses.
    Idempotent: safe to re-run.
    """
    import asyncio
    import concurrent.futures

    # Mirror the order-email loader pattern: run async logic in a worker
    # thread so this works under both Celery prefork and pytest EAGER mode.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(_run_backfill())).result()
