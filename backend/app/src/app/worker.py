# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from pywebpush import WebPushException, webpush

# Ensure search tasks are discovered by the worker.
import app.search.tasks  # noqa: F401
from app.core.celery_app import celery_app
from app.core.config import settings
from app.utils.delivery_eta import format_delivery_eta
from app.utils.delivery_window import format_delivery_window


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


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_login_otp_whatsapp_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_login_otp_whatsapp_async(code: str, phone: str) -> None:
    """Best-effort WhatsApp mirror of the customer login OTP. No-op if WhatsApp
    is disabled."""
    import asyncio
    import concurrent.futures

    from app.core.whatsapp import get_whatsapp_sender
    from app.core.whatsapp_templates import TEMPLATES

    sender = get_whatsapp_sender()
    if sender is None:
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(
            lambda: asyncio.run(
                sender.send_template(phone, TEMPLATES["otp_login"], {"code": code})
            )
        ).result()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_order_status_whatsapp_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_order_status_whatsapp_async(order_id: int, status: str) -> None:
    """Best-effort customer order-status WhatsApp. No-op when WhatsApp disabled,
    status has no template, or the customer has no verified phone."""
    import asyncio
    import concurrent.futures

    from app.core.whatsapp import get_whatsapp_sender
    from app.core.whatsapp_templates import STATUS_TEMPLATES

    sender = get_whatsapp_sender()
    if sender is None:
        return
    template = STATUS_TEMPLATES.get(status)
    if template is None:
        return
    ctx = _load_order_email_context(order_id)
    phone = ctx.get("customer_phone")
    if not phone or not ctx.get("customer_phone_verified"):
        return
    variables = {
        "order_no": str(order_id),
        "store": ctx.get("store_name") or "your store",
    }
    if status == "pending":
        variables["when"] = (
            ctx.get("preferred_delivery")
            or ctx.get("delivery_eta")
            or "as soon as possible"
        )
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(
            lambda: asyncio.run(sender.send_template(phone, template, variables))
        ).result()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_delivery_otp_email_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_delivery_otp_email_async(order_id: int, code: str) -> None:
    """Email the delivery handover code to the customer."""
    ctx = _load_order_email_context(order_id)
    to = ctx.get("customer_email")
    if not to:
        return
    subject = f"Delivery code for order #{order_id}"
    body = (
        f"Your order #{order_id} is out for delivery.\n\n"
        f"Share this code with your delivery partner to receive it: {code}\n\n"
        f"Do not share it with anyone else."
    )
    _resolve_email(to, subject, body)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_delivery_otp_sms_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_delivery_otp_sms_async(order_id: int, code: str) -> None:
    """Deliver the handover code to the customer: WhatsApp-preferred, SMS
    fallback. No-op when the customer has no phone on file."""
    import asyncio
    import concurrent.futures

    from app.core.otp_delivery import deliver_phone_otp
    from app.core.sms import get_sms_sender
    from app.core.whatsapp import get_whatsapp_sender

    ctx = _load_order_email_context(order_id)
    phone = ctx.get("customer_phone")
    if not phone:
        return
    sms_text = (
        f"{settings.COMPANY_NAME}: your delivery code for order #{order_id} is {code}. "
        f"Share it only with your delivery partner at handover."
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(
            lambda: asyncio.run(
                deliver_phone_otp(
                    to=phone,
                    template_name="otp_delivery",
                    variables={"order_no": str(order_id), "code": code},
                    sms_text=sms_text,
                    sms_sender=get_sms_sender(),
                    whatsapp_sender=get_whatsapp_sender(),
                )
            )
        ).result()


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


@celery_app.task(name="send_seller_onboarding_request_email")  # type: ignore[untyped-decorator]
def send_seller_onboarding_request_email(
    store_name: str,
    contact_phone: str,
    contact_email: str,
    contact_address: str,
    preferred_categories: str | None,
    area_label: str | None,
    source: str | None,
) -> None:
    """Notify the support inbox of a new seller-onboarding suggestion.

    reply_to is the prospective seller's email so admins can reply directly.
    """
    from app.core.config import settings
    from app.core.email_render import render_email

    payload = render_email(
        "seller_onboarding_request",
        {
            "store_name": store_name,
            "contact_phone": contact_phone,
            "contact_email": contact_email,
            "contact_address": contact_address,
            "preferred_categories": preferred_categories,
            "area_label": area_label,
            "source": source,
        },
        lang="en",
    )
    _resolve_email(
        settings.SUPPORT_EMAIL,
        payload.subject,
        payload.text,
        html=payload.html,
        reply_to=contact_email,
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
    elif settings.EMAIL_PROVIDER in ("smtp", "smtp+console"):
        import asyncio
        import concurrent.futures

        from app.core.email import SmtpEmailSender

        # _resolve_email runs in a sync Celery context; bridge to the async
        # SmtpEmailSender on a worker thread with its own event loop (same idiom
        # as the dev-mailbox capture below and the order-context loaders). A
        # fresh connection per send is loop-safe under Celery's prefork worker.
        sender = SmtpEmailSender()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(
                lambda: asyncio.run(
                    sender.send(to, subject, text=body, html=html, reply_to=reply_to)
                )
            ).result()
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
    # Dev-only capture into the dev_email table (best-effort). _resolve_email is
    # a sync Celery context, so bridge to the async recorder on a worker thread
    # (same idiom used for the async senders). Never let capture break the send.
    if settings.ENVIRONMENT == "development":
        import asyncio
        import concurrent.futures

        from app.core.dev_mailbox import record_outbound_email

        # Tag the dev-mailbox row with the real transport, matching the API-path
        # composites (SmtpWithConsoleSender/ResendWithConsoleSender).
        if settings.EMAIL_PROVIDER == "resend":
            provider_label = "resend"
        elif settings.EMAIL_PROVIDER in ("smtp", "smtp+console"):
            provider_label = "smtp"
        else:
            provider_label = "console"

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(
                    lambda: asyncio.run(
                        record_outbound_email(
                            to=to,
                            subject=subject,
                            text=body,
                            html=html,
                            reply_to=reply_to,
                            provider=provider_label,
                        )
                    )
                ).result()
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception(
                "dev_mailbox: worker email capture failed"
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
                    "subtotal": order.subtotal,
                    "delivery_fee": order.delivery_fee,
                    "order_status": order.status.value,
                    "service_name": order.service_name_snapshot,
                    "delivery_eta": format_delivery_eta(
                        order.delivery_eta_min_minutes,
                        order.delivery_eta_max_minutes,
                    ),
                    "preferred_delivery": (
                        format_delivery_window(
                            order.preferred_delivery_date,
                            order.preferred_delivery_window,
                        )
                        if order.preferred_delivery_date
                        and order.preferred_delivery_window
                        else None
                    ),
                    "store_name": store.name if store is not None else None,
                    "seller_email": seller_user.email if seller_user is not None else None,
                    "customer_email": customer_user.email if customer_user is not None else None,
                    "items": items,
                    "customer_first_name": (
                        customer_profile.first_name if customer_profile else None
                    ),
                    "customer_phone": (
                        customer_profile.phone if customer_profile else None
                    ),
                    "customer_phone_verified": (
                        customer_profile.phone_verified_at is not None
                        if customer_profile
                        else False
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
            "subtotal": ctx["subtotal"],
            "delivery_fee": ctx["delivery_fee"],
            "preferred_delivery": ctx.get("preferred_delivery"),
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
                "subtotal": ctx["subtotal"],
                "delivery_fee": ctx["delivery_fee"],
                "delivery_eta": ctx.get("delivery_eta"),
                "preferred_delivery": ctx.get("preferred_delivery"),
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


def _load_new_device_login_context(user_id: int) -> dict[str, Any]:
    import asyncio
    import concurrent.futures

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.core.config import settings
    from app.models.base import User, UserRole

    async def _load() -> dict[str, Any]:
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        try:
            async with AsyncSession(engine) as session:
                user = (
                    await session.exec(select(User).where(User.id == user_id))
                ).first()
                if user is None or not user.email:
                    return {}
                devices_path = (
                    "/account/devices"
                    if user.role != UserRole.Seller
                    else "/seller/devices"
                )
                return {
                    "email": user.email,
                    "lang": user.preferred_language or "en",
                    "devices_url": f"{settings.EMAIL_FRONTEND_BASE_URL}{devices_path}",
                }
        finally:
            await engine.dispose()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(_load())).result()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_new_device_login_email_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_new_device_login_email_async(
    user_id: int, device_label: str, ip: str | None
) -> None:
    """Best-effort "new sign-in" alert fired when a user opts into a trusted
    (long-lived) session. Never allowed to break the login path — errors are
    logged and swallowed rather than raised back to the caller."""
    from datetime import datetime, timezone

    from app.core.config import settings
    from app.core.email_render import render_email

    try:
        ctx = _load_new_device_login_context(user_id)
        if not ctx:
            return
        when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        payload = render_email(
            "new_device_login",
            {
                "device_label": device_label,
                "ip": ip,
                "when": when,
                "devices_url": ctx["devices_url"],
            },
            lang=ctx["lang"],
        )
        _resolve_email(
            ctx["email"],
            payload.subject,
            payload.text,
            html=payload.html,
            reply_to=settings.EMAIL_REPLY_TO,
        )
    except Exception:
        logging.getLogger(__name__).exception(
            "Failed to send new-device login email user_id=%s", user_id
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
# Seller profile change-request emails — one task per state. Each task loads
# a fresh CR snapshot (no SQLModel objects passed across the Celery boundary
# to avoid detached-instance + JSON-serialization issues) and renders the
# matching Jinja template.
# ---------------------------------------------------------------------------


_GROUP_LABELS: dict[str, str] = {
    "identity": "Identity",
    "address": "Business address",
    "legal": "Legal documents",
    "banking": "Banking",
    "services": "Services",
    "store_basics": "Delivery settings",
}


def _load_seller_change_request_context(cr_id_str: str) -> dict[str, Any] | None:
    """Fetch CR + seller email/business_name + group label into a render ctx.

    Returns None if the CR or its profile/user has been deleted between
    dispatch and execution — caller exits silently."""
    import asyncio
    import concurrent.futures
    import uuid as _uuid

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.core.config import settings as _settings
    from app.models.base import User
    from app.models.profile import SellerProfile
    from app.models.seller_profile_change_request import (
        SellerProfileChangeRequest,
    )

    async def _load() -> dict[str, Any] | None:
        cr_id = _uuid.UUID(cr_id_str)
        engine = create_async_engine(_settings.DATABASE_URL, echo=False)
        try:
            async with AsyncSession(engine) as session:
                cr = (
                    await session.exec(
                        select(SellerProfileChangeRequest).where(
                            SellerProfileChangeRequest.id == cr_id
                        )
                    )
                ).first()
                if cr is None:
                    return None
                profile = (
                    await session.exec(
                        select(SellerProfile).where(
                            SellerProfile.id == cr.seller_profile_id
                        )
                    )
                ).first()
                if profile is None:
                    return None
                user = (
                    await session.exec(
                        select(User).where(User.id == profile.user_id)
                    )
                ).first()
                return {
                    "to_email": user.email if user else None,
                    "business_name": profile.business_name,
                    "group": cr.group.value,
                    "group_label": _GROUP_LABELS.get(
                        cr.group.value, cr.group.value
                    ),
                    "status": cr.status.value,
                    "submission_count": cr.submission_count,
                    "proposed": cr.proposed_json,
                    "applied": cr.applied_json,
                    "baseline": cr.baseline_json,
                    "admin_note": cr.admin_note or "",
                    "cr_id": str(cr.id),
                    "FRONTEND_BASE_URL": _settings.EMAIL_FRONTEND_BASE_URL,
                }
        finally:
            await engine.dispose()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(_load())).result()


def _render_and_send_cr_email(template_name: str, ctx: dict[str, Any]) -> None:
    from app.core.config import settings as _settings
    from app.core.email_render import render_email

    to_email = ctx.get("to_email")
    if not to_email:
        return
    payload = render_email(template_name, ctx, lang="en")
    _resolve_email(
        to_email,
        payload.subject,
        payload.text,
        html=payload.html,
        reply_to=_settings.EMAIL_REPLY_TO,
    )


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_seller_change_request_submitted_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_seller_change_request_submitted_async(cr_id_str: str) -> None:
    """Confirm receipt of a (new or resubmitted) seller change request."""
    ctx = _load_seller_change_request_context(cr_id_str)
    if not ctx:
        return
    _render_and_send_cr_email("seller_change_request_submitted", ctx)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_seller_change_request_approved_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_seller_change_request_approved_async(cr_id_str: str) -> None:
    """Notify the seller that their change request was approved.

    Picks the with-edits or no-edits template based on whether the admin's
    `applied_json` differs from the seller's `proposed_json`.
    """
    ctx = _load_seller_change_request_context(cr_id_str)
    if not ctx:
        return
    has_edits = (
        ctx.get("applied") is not None
        and ctx["applied"] != ctx.get("proposed")
    )
    ctx["has_edits"] = has_edits
    template = (
        "seller_change_request_approved_with_edits"
        if has_edits
        else "seller_change_request_approved"
    )
    _render_and_send_cr_email(template, ctx)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_seller_change_request_changes_requested_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_seller_change_request_changes_requested_async(cr_id_str: str) -> None:
    """Notify the seller that an admin asked them to update their request."""
    ctx = _load_seller_change_request_context(cr_id_str)
    if not ctx:
        return
    _render_and_send_cr_email("seller_change_request_changes_requested", ctx)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_seller_change_request_rejected_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_seller_change_request_rejected_async(cr_id_str: str) -> None:
    """Notify the seller that their change request was rejected."""
    ctx = _load_seller_change_request_context(cr_id_str)
    if not ctx:
        return
    _render_and_send_cr_email("seller_change_request_rejected", ctx)


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
    # VAPID_PRIVATE_KEY is the raw base64url-encoded EC private key (the format
    # py_vapid.Vapid.from_string expects: it base64url-decodes to the 32-byte
    # scalar). A PKCS8 PEM is NOT accepted here and fails ASN.1 parsing.
    private_key = settings.VAPID_PRIVATE_KEY.strip()
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


# ---------------------------------------------------------------------------
# Seller fee-notification channels (best-effort). Each task resolves the
# seller's phone/email via the thread-bridged async_session_factory pattern
# and no-ops when the channel/contact is unavailable.
# ---------------------------------------------------------------------------


_FEE_CHANNEL_COPY: dict[str, tuple[str, str]] = {
    # type_value: (subject, body). {until} filled when provided.
    "fee_activated": (
        "Your subscription is active",
        "Your store subscription is active{until}. Thank you for subscribing.",
    ),
    "fee_expiring": (
        "Your plan is expiring soon",
        "Your store plan expires{until}. Renew from your seller dashboard to stay active.",
    ),
    "fee_suspended": (
        "A service on your store was suspended",
        "A service on your store has been suspended. Renew or clear your balance to reactivate it.",
    ),
}


async def _seller_contact(
    session: Any, seller_profile_id: int
) -> tuple[str | None, str | None]:
    """Return (phone, email) for a seller, or (None, None)."""
    from sqlmodel import select

    from app.models.base import User
    from app.models.profile import SellerProfile

    row = (
        await session.exec(
            select(SellerProfile.phone, User.email)
            .join(User, User.id == SellerProfile.user_id)  # type: ignore[arg-type]
            .where(SellerProfile.id == seller_profile_id)
        )
    ).first()
    if row is None:
        return None, None
    return row[0], row[1]


def _until_clause(until: str | None, *, on: bool = False) -> str:
    if not until:
        return " soon" if on else ""
    return f" on {until}" if on else f" until {until}"


@celery_app.task(name="send_seller_fee_sms_async")  # type: ignore[untyped-decorator]
def send_seller_fee_sms_async(
    seller_profile_id: int, type_value: str, until: str | None
) -> None:
    """Best-effort SMS for a seller fee-notification event."""
    import asyncio
    import concurrent.futures

    from app.core.sms import get_sms_sender
    from app.db.session import async_session_factory

    async def _run() -> None:
        async with async_session_factory() as session:
            phone, _email = await _seller_contact(session, seller_profile_id)
        if not phone:
            return
        subject, body_tmpl = _FEE_CHANNEL_COPY.get(type_value, ("", ""))
        if not subject:
            return
        on = type_value == "fee_expiring"
        body = body_tmpl.format(until=_until_clause(until, on=on))
        try:
            await get_sms_sender().send(phone, f"{subject}. {body}")
        except Exception:
            logging.getLogger(__name__).exception(
                "seller fee SMS failed for seller_profile_id=%s", seller_profile_id
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        ex.submit(lambda: asyncio.run(_run())).result()


@celery_app.task(name="send_seller_fee_whatsapp_async")  # type: ignore[untyped-decorator]
def send_seller_fee_whatsapp_async(
    seller_profile_id: int, type_value: str, until: str | None
) -> None:
    """Best-effort WhatsApp for a seller fee-notification event. No-op when
    WhatsApp is disabled or the event has no registered template."""
    import asyncio
    import concurrent.futures

    from app.core.whatsapp import get_whatsapp_sender
    from app.core.whatsapp_templates import FEE_TEMPLATES
    from app.db.session import async_session_factory

    async def _run() -> None:
        sender = get_whatsapp_sender()
        if sender is None:
            return
        tmpl = FEE_TEMPLATES.get(type_value)
        if tmpl is None:
            return
        async with async_session_factory() as session:
            phone, _email = await _seller_contact(session, seller_profile_id)
        if not phone:
            return
        variables = {"until": until or ""} if "until" in tmpl.variables else {}
        try:
            await sender.send_template(phone, tmpl, variables)
        except Exception:
            logging.getLogger(__name__).exception(
                "seller fee WhatsApp failed for seller_profile_id=%s",
                seller_profile_id,
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        ex.submit(lambda: asyncio.run(_run())).result()


@celery_app.task(name="send_seller_fee_email_async")  # type: ignore[untyped-decorator]
def send_seller_fee_email_async(
    seller_profile_id: int, type_value: str, until: str | None
) -> None:
    """Best-effort email for a seller fee-notification event."""
    import asyncio
    import concurrent.futures

    from app.db.session import async_session_factory

    async def _run() -> None:
        async with async_session_factory() as session:
            _phone, email = await _seller_contact(session, seller_profile_id)
        if not email:
            return
        subject, body_tmpl = _FEE_CHANNEL_COPY.get(type_value, ("", ""))
        if not subject:
            return
        on = type_value == "fee_expiring"
        body = body_tmpl.format(until=_until_clause(until, on=on))
        try:
            _resolve_email(email, subject, body, reply_to=settings.EMAIL_REPLY_TO)
        except Exception:
            logging.getLogger(__name__).exception(
                "seller fee email failed for seller_profile_id=%s", seller_profile_id
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        ex.submit(lambda: asyncio.run(_run())).result()


def _referral_activation_url(token: str, target_role: str) -> str:
    """Absolute activation link carried in the invite comms. Seller invites
    open the seller-signup wizard (non-localized); customer invites open the
    localized invite-accept landing (default `en`)."""
    base = settings.EMAIL_FRONTEND_BASE_URL.rstrip("/")
    if target_role == "seller":
        return f"{base}/seller/signup?invite={token}"
    return f"{base}/en/invite?token={token}"


@celery_app.task(name="referrals.send_invite")  # type: ignore[untyped-decorator]
def send_referral_invite(referral_id: int, token: str) -> None:
    """Best-effort welcome comms for an approved referral. Email when an email
    was captured; SMS when a phone was captured (≥1 is guaranteed). WhatsApp is
    deferred to go-live (template + ContentSid), consistent with other channels."""
    import asyncio
    import concurrent.futures

    from app.core.sms import get_sms_sender
    from app.db.session import async_session_factory
    from app.models.referral import Referral

    async def _run() -> None:
        async with async_session_factory() as session:
            row = await session.get(Referral, referral_id)
            if row is None:
                return
            name = row.invitee_name
            email = row.invitee_email
            phone = row.invitee_phone
            target_role = row.target_role.value
        url = _referral_activation_url(token, target_role)
        brand = settings.COMPANY_NAME
        subject = f"You're invited to join {brand}"
        body = (
            f"Hi {name},\n\nYou've been invited to join {brand}. "
            f"Activate your account here:\n{url}\n\n"
            f"This link expires in {settings.REFERRAL_INVITE_EXPIRY_DAYS} days."
        )
        if email:
            try:
                _resolve_email(email, subject, body, reply_to=settings.EMAIL_REPLY_TO)
            except Exception:
                logging.getLogger(__name__).exception(
                    "referral invite email failed id=%s", referral_id
                )
        if phone:
            try:
                await get_sms_sender().send(phone, f"Join {brand}: {url}")
            except Exception:
                logging.getLogger(__name__).exception(
                    "referral invite SMS failed id=%s", referral_id
                )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        ex.submit(lambda: asyncio.run(_run())).result()


def dispatch_referral_invite(referral_id: int, token: str) -> None:
    """Broker-safe enqueue of the welcome comms; never blocks the approval path."""
    from app.services.order_emails import _safe_delay

    _safe_delay(send_referral_invite, referral_id, token)


@celery_app.task(name="referrals.run_invite_expiry_sweep")  # type: ignore[untyped-decorator]
def run_referral_invite_expiry_sweep() -> int:
    """Daily: transition approved referrals whose invite has lapsed to expired.
    Runs the async sweep on a worker thread so it works under both the real
    worker and eager-mode tests."""
    import concurrent.futures

    from app.db.session import async_session_factory
    from app.services.referrals import run_referral_expiry_sweep

    async def _run() -> int:
        async with async_session_factory() as session:
            n = await run_referral_expiry_sweep(session)
            await session.commit()
            return n

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(_run())).result()


@celery_app.task(name="fees.run_daily_sweep")  # type: ignore[untyped-decorator]
def run_daily_fee_sweep() -> dict[str, int]:
    """Daily: expire freebie trials (Trial→Grace→Suspended, holding when no paid
    model is offerable). Runs the async sweep on a worker thread so it works in
    both the real worker and eager tests. After the sweep commits, best-effort
    fans out any collected fee notifications (reminder/suspension) to SMS +
    WhatsApp + email — dispatch happens post-commit so a channel hiccup can
    never roll back the sweep."""
    from datetime import date

    from app.db.session import async_session_factory
    from app.services.fee_channels import dispatch_seller_fee_channels
    from app.services.fee_lifecycle import run_fee_sweep

    async def _run() -> tuple[dict[str, int], list[tuple[int, str, str | None]]]:
        notices: list[tuple[int, str, str | None]] = []
        async with async_session_factory() as session:
            counts = await run_fee_sweep(session, notices=notices)
            await session.commit()
            return counts, notices

    with ThreadPoolExecutor(max_workers=1) as executor:
        counts, notices = executor.submit(lambda: asyncio.run(_run())).result()

    for spid, type_value, until in notices:
        dispatch_seller_fee_channels(
            spid, type_value, date.fromisoformat(until) if until else None
        )
    return counts


@celery_app.task(name="credit.run_monthly_statements")  # type: ignore[untyped-decorator]
def run_monthly_credit_statements() -> int:
    """Monthly credit statement notifications. Runs the async job on a worker
    thread so it works under both the real worker and eager-mode tests."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    from app.db.session import async_session_factory
    from app.services.credit_notifications import run_credit_statements

    async def _run() -> int:
        async with async_session_factory() as session:
            return await run_credit_statements(session)

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(_run())).result()


@celery_app.task(name="send_campaign_async")  # type: ignore[untyped-decorator]
def send_campaign_async(campaign_id: int) -> None:
    """Orchestrate a bulk-notification campaign fan-out."""
    import asyncio
    import concurrent.futures

    from app.db.session import async_session_factory
    from app.services.notification_campaigns import send_campaign

    async def _run() -> None:
        async with async_session_factory() as session:
            await send_campaign(session, campaign_id)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        ex.submit(lambda: asyncio.run(_run())).result()


@celery_app.task(name="send_campaign_email_async")  # type: ignore[untyped-decorator]
def send_campaign_email_async(campaign_id: int, to_email: str) -> None:
    """Best-effort campaign email to one recipient."""
    import asyncio
    import concurrent.futures

    from app.db.session import async_session_factory
    from app.models.notification_campaign import NotificationCampaign

    async def _run() -> None:
        async with async_session_factory() as session:
            campaign = await session.get(NotificationCampaign, campaign_id)
        if campaign is None:
            return
        body = campaign.body
        if campaign.cta_url:
            body = f"{body}\n\n{campaign.cta_label or 'Open'}: {campaign.cta_url}"
        try:
            _resolve_email(
                to_email, campaign.title, body, reply_to=settings.EMAIL_REPLY_TO
            )
        except Exception:
            logging.getLogger(__name__).exception(
                "campaign email failed for campaign_id=%s", campaign_id
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        ex.submit(lambda: asyncio.run(_run())).result()


@celery_app.task(name="send_campaign_sms_async")  # type: ignore[untyped-decorator]
def send_campaign_sms_async(campaign_id: int, to_phone: str) -> None:
    """Best-effort campaign SMS to one recipient."""
    import asyncio
    import concurrent.futures

    from app.core.sms import get_sms_sender
    from app.db.session import async_session_factory
    from app.models.notification_campaign import NotificationCampaign

    async def _run() -> None:
        async with async_session_factory() as session:
            campaign = await session.get(NotificationCampaign, campaign_id)
        if campaign is None:
            return
        text = f"{campaign.title}: {campaign.body}"
        if campaign.cta_url:
            text = f"{text} {campaign.cta_url}"
        try:
            await get_sms_sender().send(to_phone, text)
        except Exception:
            logging.getLogger(__name__).exception(
                "campaign sms failed for campaign_id=%s", campaign_id
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        ex.submit(lambda: asyncio.run(_run())).result()


def _load_account_email_context(user_id: int) -> dict[str, Any]:
    """Load {email, first_name} for account-status emails. Empty dict if gone.

    Mirrors _load_order_email_context: runs the async loader in a worker thread
    with its own event loop + engine, disposed in finally.
    """
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
                if user is None:
                    return {}
                profile = (
                    await session.exec(
                        select(CustomerProfile).where(
                            CustomerProfile.user_id == user_id
                        )
                    )
                ).first()
                return {
                    "email": user.email,
                    "first_name": profile.first_name if profile else "there",
                }
        finally:
            await engine.dispose()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(_load())).result()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_account_status_email_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_account_status_email_async(user_id: int, event_key: str) -> None:
    """Notify a customer of an account state change (English-only)."""
    from app.core.config import settings
    from app.core.email_render import render_email

    ctx = _load_account_email_context(user_id)
    if not ctx or not ctx.get("email"):
        return
    payload = render_email(
        event_key, {"first_name": ctx.get("first_name") or "there"}, lang="en"
    )
    _resolve_email(
        ctx["email"],
        payload.subject,
        payload.text,
        html=payload.html,
        reply_to=settings.EMAIL_REPLY_TO,
    )
