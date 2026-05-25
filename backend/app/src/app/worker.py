# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import logging
import time
from typing import Any, Literal

from pywebpush import WebPushException, webpush

# Ensure search tasks are discovered by the worker.
import app.search.tasks  # noqa: F401
from app.core.celery_app import celery_app
from app.core.config import settings


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
    """Forward a customer support message to the configured SUPPORT_EMAIL inbox.

    Sets ``reply_to`` to the customer's address so admin replies land back
    on the customer directly.
    """
    from app.core.config import settings
    from app.core.email_render import render_email

    payload = render_email(
        "support_message",
        {
            "customer_email": customer_email,
            "user_subject": subject,
            "message": message,
        },
        lang="en",
    )
    _resolve_email(
        settings.SUPPORT_EMAIL,
        payload.subject,
        payload.text,
        html=payload.html,
        reply_to=customer_email,
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
        # Same PII-safety gating as ConsoleEmailSender.send: only log the body
        # in development; non-dev environments see subject + recipient only.
        if settings.ENVIRONMENT == "development":
            logging.getLogger(__name__).info(
                "EMAIL to=%s subject=%s body=%s", to, subject, body
            )
        else:
            logging.getLogger(__name__).info(
                "EMAIL to=%s subject=%s (body suppressed)", to, subject
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
    from app.core.config import settings
    from app.core.email_render import render_email

    ctx = _load_order_email_context(order_id)
    if not ctx or not ctx.get("seller_email"):
        return
    payload = render_email(
        "order_placed_seller",
        {
            "order_id": ctx["order_id"],
            "service_name": ctx["service_name"],
            "store_name": ctx.get("store_name") or "your store",
            "items": ctx.get("items", []),
            "order_total": ctx["order_total"],
        },
        lang=ctx.get("seller_lang") or "en",
    )
    _resolve_email(
        ctx["seller_email"],
        payload.subject,
        payload.text,
        html=payload.html,
        reply_to=settings.EMAIL_REPLY_TO,
    )


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_order_confirmed_customer_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_order_confirmed_customer_async(order_ids: list[int]) -> None:
    """Notify the customer that their order(s) were confirmed.

    Accepts a list of order ids (a single checkout may produce multiple
    per-store orders). Renders one consolidated email with per-order line
    items and a single CTA.
    """
    from app.core.config import settings
    from app.core.email_render import render_email

    customer_email: str | None = None
    customer_first_name: str | None = None
    customer_lang: str = "en"
    orders: list[dict[str, Any]] = []
    grand_total: float = 0.0

    for oid in order_ids:
        ctx = _load_order_email_context(oid)
        if not ctx:
            continue
        if customer_email is None:
            customer_email = ctx.get("customer_email")
            customer_first_name = ctx.get("customer_first_name")
            customer_lang = ctx.get("customer_lang") or "en"
        orders.append(
            {
                "order_id": ctx["order_id"],
                "service_name": ctx["service_name"],
                "store_name": ctx.get("store_name") or "a store",
                "line_items": ctx.get("items", []),
                "order_total": ctx["order_total"],
            }
        )
        grand_total += float(ctx["order_total"])

    if not customer_email or not orders:
        return

    payload = render_email(
        "order_placed_customer",
        {
            "orders": orders,
            "grand_total": grand_total,
            "customer_first_name": customer_first_name,
        },
        lang=customer_lang,
    )
    _resolve_email(
        customer_email,
        payload.subject,
        payload.text,
        html=payload.html,
        reply_to=settings.EMAIL_REPLY_TO,
    )


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_order_status_changed_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_order_status_changed_async(
    order_id: int,
    new_status: str,
    recipient: Literal["customer", "seller"] = "customer",
    reason: str | None = None,
) -> None:
    """Notify the customer or seller that an order status changed."""
    from app.core.config import settings
    from app.core.email_render import render_email

    ctx = _load_order_email_context(order_id)
    if not ctx:
        return
    if recipient == "seller":
        to = ctx.get("seller_email")
        lang = ctx.get("seller_lang") or "en"
    else:
        to = ctx.get("customer_email")
        lang = ctx.get("customer_lang") or "en"
    if not to:
        return
    payload = render_email(
        "order_status_changed",
        {
            "order_id": ctx["order_id"],
            "service_name": ctx["service_name"],
            "store_name": ctx.get("store_name") or "a store",
            "current": new_status,
            "reason": reason,
            "recipient": recipient,
        },
        lang=lang,
    )
    _resolve_email(
        to,
        payload.subject,
        payload.text,
        html=payload.html,
        reply_to=settings.EMAIL_REPLY_TO,
    )


_ACTION_LABELS = {
    "order.rewind": "Status reverted",
    "order.refund": "Refunded",
    "order.cancel": "Cancelled",
    "order.address_override": "Delivery address updated",
    "order.transition": "Status changed",
}


def _action_label(action: str) -> str:
    return _ACTION_LABELS.get(action, action)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_admin_order_action_email",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_admin_order_action_seller_async(
    order_id: int, action: str, reason: str
) -> None:
    """Notify the seller that an admin took action on one of their orders."""
    from app.core.config import settings
    from app.core.email_render import render_email

    ctx = _load_order_email_context(order_id)
    if not ctx or not ctx.get("seller_email"):
        return
    payload = render_email(
        "admin_order_action_seller",
        {
            "order_id": ctx["order_id"],
            "service_name": ctx["service_name"],
            "store_name": ctx.get("store_name") or "your store",
            "action_label": _action_label(action),
            "reason": reason or "",
        },
        lang=ctx.get("seller_lang") or "en",
    )
    _resolve_email(
        ctx["seller_email"],
        payload.subject,
        payload.text,
        html=payload.html,
        reply_to=settings.EMAIL_REPLY_TO,
    )


# Back-compat alias so existing callers (tests, imports) keep working until
# the Celery task name change is fully migrated.
send_admin_order_action_email = send_admin_order_action_seller_async


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_order_review_request_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_order_review_request_async(order_id: int) -> None:
    """Ask the customer for a review ~24 hours after delivery.

    The Celery countdown is not exact (broker restart / retry may shift it),
    so we pass the actual delivered-on date from `Delivery.delivered_at` if
    available rather than the brittle copy "delivered yesterday".
    """
    from datetime import datetime, timezone

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.core.config import settings
    from app.core.email_render import render_email

    ctx = _load_order_email_context(order_id)
    if not ctx or not ctx.get("customer_email"):
        return

    # Best-effort: look up Delivery.delivered_at so the email can name the
    # actual date instead of "yesterday".
    delivered_on: str | None = None
    try:
        import asyncio
        import concurrent.futures

        from sqlmodel import select

        from app.models.commerce import Delivery

        async def _load_delivered_at() -> datetime | None:
            engine = create_async_engine(settings.DATABASE_URL, echo=False)
            try:
                async with AsyncSession(engine) as session:
                    delivery = (
                        await session.exec(
                            select(Delivery).where(Delivery.order_id == order_id)
                        )
                    ).first()
                    return getattr(delivery, "delivered_at", None) if delivery else None
            finally:
                await engine.dispose()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            dt = executor.submit(lambda: asyncio.run(_load_delivered_at())).result()
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            delivered_on = dt.strftime("%-d %b %Y")
    except Exception:
        # Non-fatal — the template handles missing `delivered_on` gracefully.
        delivered_on = None

    payload = render_email(
        "order_review_request",
        {
            "order_id": ctx["order_id"],
            "service_name": ctx["service_name"],
            "store_name": ctx.get("store_name") or "a store",
            "customer_first_name": ctx.get("customer_first_name"),
            "delivered_on": delivered_on,
        },
        lang=ctx.get("customer_lang") or "en",
    )
    _resolve_email(
        ctx["customer_email"],
        payload.subject,
        payload.text,
        html=payload.html,
        reply_to=settings.EMAIL_REPLY_TO,
    )


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_admin_order_action_customer_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_admin_order_action_customer_async(
    order_id: int, action: str, reason: str
) -> None:
    """Notify the customer that an admin acted on their order."""
    from app.core.config import settings
    from app.core.email_render import render_email

    ctx = _load_order_email_context(order_id)
    if not ctx or not ctx.get("customer_email"):
        return
    payload = render_email(
        "admin_order_action_customer",
        {
            "order_id": ctx["order_id"],
            "service_name": ctx["service_name"],
            "customer_first_name": ctx.get("customer_first_name"),
            "action": action,
            "action_label": _action_label(action),
            "reason": reason or "",
            "delivery_address_snapshot": ctx.get("delivery_address_snapshot") or "",
        },
        lang=ctx.get("customer_lang") or "en",
    )
    _resolve_email(
        ctx["customer_email"],
        payload.subject,
        payload.text,
        html=payload.html,
        reply_to=settings.EMAIL_REPLY_TO,
    )


def _load_customer_welcome_context(user_id: int) -> dict[str, Any]:
    import asyncio
    import concurrent.futures

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.core.config import settings
    from app.models.base import User
    from app.models.profile import CustomerProfile

    async def _load() -> dict[str, Any]:
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        try:
            async with AsyncSession(engine) as session:
                user = (
                    await session.exec(select(User).where(User.id == user_id))
                ).first()
                if user is None or not user.email:
                    return {}
                profile = (
                    await session.exec(
                        select(CustomerProfile).where(
                            CustomerProfile.user_id == user_id
                        )
                    )
                ).first()
                first_name = profile.first_name if profile else "there"
                return {
                    "email": user.email,
                    "first_name": first_name,
                    "lang": user.preferred_language or "en",
                }
        finally:
            await engine.dispose()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(_load())).result()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_customer_welcome_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_customer_welcome_async(user_id: int) -> None:
    """Greet a newly-registered customer (fires only on User row creation)."""
    from app.core.config import settings
    from app.core.email_render import render_email

    ctx = _load_customer_welcome_context(user_id)
    if not ctx:
        return
    payload = render_email(
        "customer_welcome", {"first_name": ctx["first_name"]}, lang=ctx["lang"]
    )
    _resolve_email(
        ctx["email"],
        payload.subject,
        payload.text,
        html=payload.html,
        reply_to=settings.EMAIL_REPLY_TO,
    )


def _load_seller_application_context(seller_profile_id: int) -> dict[str, Any]:
    import asyncio
    import concurrent.futures

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.core.config import settings
    from app.models.base import User
    from app.models.profile import SellerProfile

    async def _load() -> dict[str, Any]:
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        try:
            async with AsyncSession(engine) as session:
                profile = (
                    await session.exec(
                        select(SellerProfile).where(SellerProfile.id == seller_profile_id)
                    )
                ).first()
                if profile is None:
                    return {}
                user = (
                    await session.exec(select(User).where(User.id == profile.user_id))
                ).first()
                submitted_at = (
                    profile.updated_at.strftime("%Y-%m-%d %H:%M UTC")
                    if profile.updated_at
                    else ""
                )
                return {
                    "business_name": profile.business_name,
                    "applicant_email": user.email if user else "",
                    "submitted_at": submitted_at,
                }
        finally:
            await engine.dispose()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(_load())).result()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_seller_application_submitted_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_seller_application_submitted_async(seller_profile_id: int) -> None:
    """Notify the support inbox that a new seller application is pending."""
    from app.core.config import settings
    from app.core.email_render import render_email

    ctx = _load_seller_application_context(seller_profile_id)
    if not ctx:
        return
    payload = render_email("seller_application_submitted", ctx, lang="en")
    _resolve_email(
        settings.SUPPORT_EMAIL,
        payload.subject,
        payload.text,
        html=payload.html,
        reply_to=ctx.get("applicant_email") or settings.EMAIL_REPLY_TO,
    )


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_seller_approved_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_seller_approved_async(to_email: str, business_name: str) -> None:
    """Notify a seller that their application has been approved."""
    from app.core.config import settings
    from app.core.email_render import render_email

    if not to_email:
        return
    payload = render_email(
        "seller_approved", {"business_name": business_name}, lang="en"
    )
    _resolve_email(
        to_email,
        payload.subject,
        payload.text,
        html=payload.html,
        reply_to=settings.EMAIL_REPLY_TO,
    )


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
    from app.core.config import settings
    from app.core.email_render import render_email

    if not to_email:
        return
    payload = render_email(
        "seller_rejected",
        {"business_name": business_name, "reason": reason or "Not specified"},
        lang="en",
    )
    _resolve_email(
        to_email,
        payload.subject,
        payload.text,
        html=payload.html,
        reply_to=settings.EMAIL_REPLY_TO,
    )


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


def _load_push_targets(notification_id: int) -> dict[str, Any]:
    """Load the notification + its customer's push subscriptions.

    Mirrors the order-email loader: runs async DB work in a worker thread so it
    works under Celery prefork AND pytest EAGER mode. Returns {} if not found.
    """
    import asyncio
    import concurrent.futures

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.notification import Notification, PushSubscription

    async def _load() -> dict[str, Any]:
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        try:
            async with AsyncSession(engine) as session:
                notif = (
                    await session.exec(
                        select(Notification).where(Notification.id == notification_id)
                    )
                ).first()
                if notif is None:
                    return {}
                subs = (
                    await session.exec(
                        select(PushSubscription).where(
                            PushSubscription.customer_profile_id
                            == notif.customer_profile_id
                        )
                    )
                ).all()
                return {
                    "title": notif.title,
                    "body": notif.body,
                    "order_id": notif.order_id,
                    "subscriptions": [
                        {"endpoint": s.endpoint, "p256dh": s.p256dh, "auth": s.auth}
                        for s in subs
                    ],
                }
        finally:
            await engine.dispose()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(_load())).result()


def _delete_dead_subscriptions(endpoints: list[str]) -> None:
    """Best-effort prune of subscriptions the push service reported as gone."""
    if not endpoints:
        return
    import asyncio
    import concurrent.futures

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.notification import PushSubscription

    async def _delete() -> None:
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        try:
            async with AsyncSession(engine) as session:
                for ep in endpoints:
                    row = (
                        await session.exec(
                            select(PushSubscription).where(
                                PushSubscription.endpoint == ep
                            )
                        )
                    ).first()
                    if row is not None:
                        await session.delete(row)
                await session.commit()
        finally:
            await engine.dispose()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(lambda: asyncio.run(_delete())).result()


@celery_app.task(name="send_order_push_async")  # type: ignore[untyped-decorator]
def send_order_push_async(notification_id: int) -> None:
    """Send the order-status web push to all of the customer's subscriptions.

    Best-effort: missing VAPID config or a transient push error is logged and
    swallowed. Subscriptions the push service reports as 404/410 are pruned.
    """
    import json

    if not settings.VAPID_PRIVATE_KEY:
        logging.getLogger(__name__).info(
            "Web push skipped: VAPID_PRIVATE_KEY not configured"
        )
        return

    ctx = _load_push_targets(notification_id)
    subs = ctx.get("subscriptions") or []
    if not subs:
        return

    order_id = ctx.get("order_id")
    payload = json.dumps(
        {
            "title": ctx["title"],
            "body": ctx["body"],
            "url": f"/account/orders/{order_id}" if order_id else "/account/orders",
        }
    )
    # Env files store the PKCS8 PEM on a single line with escaped newlines;
    # restore real newlines so it parses as a valid PEM (no-op if already real).
    private_key = settings.VAPID_PRIVATE_KEY.replace("\\n", "\n")
    dead: list[str] = []
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                },
                data=payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": settings.VAPID_SUBJECT},
                # Queue for up to 24h so a briefly-offline device still gets the
                # order update when it reconnects (default ttl=0 = deliver-now-or-drop).
                ttl=86400,
            )
        except WebPushException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in (404, 410):
                dead.append(sub["endpoint"])
            else:
                logging.getLogger(__name__).warning(
                    "Web push failed endpoint=%s status=%s",
                    sub["endpoint"],
                    status_code,
                )
        except Exception:
            logging.getLogger(__name__).exception(
                "Unexpected web push error endpoint=%s", sub.get("endpoint")
            )
    _delete_dead_subscriptions(dead)
