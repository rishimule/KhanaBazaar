# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""WhatsApp template registry.

WhatsApp business-initiated messages must use pre-approved templates, not free
text. Each template declares its category (AUTHENTICATION for OTP, UTILITY for
order updates), the positional variable order the real provider expects, and a
`render` used by the console/mock provider + the /dev-whatsapp page. In
production the text comes from the approved template; `render` is mock-only.
English-only for now.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from app.core.config import settings


@dataclass(frozen=True)
class WhatsAppTemplate:
    name: str
    category: Literal["AUTHENTICATION", "UTILITY"]
    variables: tuple[str, ...]
    render: Callable[[dict[str, str]], str]
    content_sid_setting: str | None = None  # settings attr resolved at go-live


TEMPLATES: dict[str, WhatsAppTemplate] = {
    "otp_login": WhatsAppTemplate(
        name="otp_login",
        category="AUTHENTICATION",
        variables=("code",),
        render=lambda v: (
            f"Your {settings.COMPANY_NAME} login code is {v['code']}. "
            "It expires in 10 minutes. Do not share it with anyone."
        ),
    ),
    "otp_seller_phone": WhatsAppTemplate(
        name="otp_seller_phone",
        category="AUTHENTICATION",
        variables=("code",),
        render=lambda v: (
            f"Your {settings.COMPANY_NAME} seller verification code is {v['code']}. "
            "It expires in 10 minutes."
        ),
    ),
    "otp_delivery": WhatsAppTemplate(
        name="otp_delivery",
        category="AUTHENTICATION",
        variables=("order_no", "code"),
        render=lambda v: (
            f"Your {settings.COMPANY_NAME} delivery code for order #{v['order_no']} is "
            f"{v['code']}. Share it only with your delivery partner at handover."
        ),
    ),
    "otp_return": WhatsAppTemplate(
        name="otp_return",
        category="AUTHENTICATION",
        variables=("return_no", "code"),
        render=lambda v: (
            f"Your {settings.COMPANY_NAME} confirmation code for return "
            f"#{v['return_no']} is {v['code']}. It expires in 10 minutes. "
            "Do not share it with anyone."
        ),
    ),
    "return_initiated": WhatsAppTemplate(
        name="return_initiated",
        category="UTILITY",
        variables=("return_no", "store"),
        render=lambda v: (
            f"A return (#{v['return_no']}) was started for your order at "
            f"{v['store']}. Open {settings.COMPANY_NAME} to review the agreement "
            "and confirm it, or it will expire."
        ),
    ),
    "return_confirmed": WhatsAppTemplate(
        name="return_confirmed",
        category="UTILITY",
        variables=("return_no", "code"),
        render=lambda v: (
            f"Return #{v['return_no']} is confirmed. Show handover code "
            f"{v['code']} to the store when you hand the items over."
        ),
    ),
    "return_accepted": WhatsAppTemplate(
        name="return_accepted",
        category="UTILITY",
        variables=("return_no", "amount"),
        render=lambda v: (
            f"Return #{v['return_no']} was accepted. Amount: {v['amount']}. "
            f"Check {settings.COMPANY_NAME} for the settlement details."
        ),
    ),
    "return_rejected": WhatsAppTemplate(
        name="return_rejected",
        category="UTILITY",
        variables=("return_no", "reason"),
        render=lambda v: (
            f"Return #{v['return_no']} was not accepted. Reason: {v['reason']}. "
            "Please settle this directly with the store."
        ),
    ),
    "return_closed": WhatsAppTemplate(
        name="return_closed",
        category="UTILITY",
        variables=("return_no", "amount"),
        render=lambda v: (
            f"Return #{v['return_no']} is closed. Amount: {v['amount']}."
        ),
    ),
    "order_placed": WhatsAppTemplate(
        name="order_placed",
        category="UTILITY",
        variables=("order_no", "store", "when"),
        render=lambda v: (
            f"Order #{v['order_no']} placed at {v['store']}. "
            f"Delivery: {v['when']}. "
            "We'll let you know as it progresses."
        ),
    ),
    "order_packed": WhatsAppTemplate(
        name="order_packed",
        category="UTILITY",
        variables=("order_no", "store"),
        render=lambda v: (
            f"Order #{v['order_no']} from {v['store']} is packed and "
            "being prepared for dispatch."
        ),
    ),
    "order_dispatched": WhatsAppTemplate(
        name="order_dispatched",
        category="UTILITY",
        variables=("order_no", "store"),
        render=lambda v: (
            f"Order #{v['order_no']} from {v['store']} is on the way!"
        ),
    ),
    "order_delivered": WhatsAppTemplate(
        name="order_delivered",
        category="UTILITY",
        variables=("order_no", "store"),
        render=lambda v: (
            f"Order #{v['order_no']} from {v['store']} has been delivered. "
            "Enjoy!"
        ),
    ),
    "order_cancelled": WhatsAppTemplate(
        name="order_cancelled",
        category="UTILITY",
        variables=("order_no", "store"),
        render=lambda v: (
            f"Order #{v['order_no']} from {v['store']} has been cancelled."
        ),
    ),
    "fee_activated": WhatsAppTemplate(
        name="fee_activated",
        category="UTILITY",
        variables=("until",),
        render=lambda v: (
            f"Your {settings.COMPANY_NAME} store subscription is active until {v['until']}. "
            "Thank you!"
        ),
    ),
    # NOTE: production WhatsApp text comes from Twilio-approved templates, so
    # editing these render functions only changes the `console` mock. The wording
    # is kept in step with fee_notifications._COPY so the approved templates can
    # be re-submitted from one source of truth at go-live.
    "fee_expiring": WhatsAppTemplate(
        name="fee_expiring",
        category="UTILITY",
        variables=("until",),
        render=lambda v: (
            f"Your {settings.COMPANY_NAME} store plan expires on {v['until']}. "
            "Renew from your seller dashboard — once the short grace period "
            "after that runs out, customers can't find or order from this service."
        ),
    ),
    "fee_suspended": WhatsAppTemplate(
        name="fee_suspended",
        category="UTILITY",
        variables=(),
        render=lambda v: (
            f"A service on your {settings.COMPANY_NAME} store is now hidden from "
            "customers — they can't find it or place an order. Renew or clear "
            "your balance from your seller dashboard to restore it."
        ),
    ),
    "seller_new_order": WhatsAppTemplate(
        name="seller_new_order",
        category="UTILITY",
        variables=("order_id", "amount"),
        render=lambda v: (
            f"New order #{v['order_id']} for ₹{v['amount']} on your "
            f"{settings.COMPANY_NAME} store. Open your seller dashboard to pack it."
        ),
    ),
}


# Maps OrderStatus.value (as passed to record_and_dispatch_notification) to the
# UTILITY template for that customer status update.
STATUS_TEMPLATES: dict[str, WhatsAppTemplate] = {
    "pending": TEMPLATES["order_placed"],
    "packed": TEMPLATES["order_packed"],
    "dispatched": TEMPLATES["order_dispatched"],
    "delivered": TEMPLATES["order_delivered"],
    "cancelled": TEMPLATES["order_cancelled"],
}


# Maps NotificationType.value (fee events) → UTILITY template.
FEE_TEMPLATES: dict[str, WhatsAppTemplate] = {
    "fee_activated": TEMPLATES["fee_activated"],
    "fee_expiring": TEMPLATES["fee_expiring"],
    "fee_suspended": TEMPLATES["fee_suspended"],
}
