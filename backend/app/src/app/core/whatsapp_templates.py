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
            f"Your Khana Bazaar login code is {v['code']}. "
            "It expires in 10 minutes. Do not share it with anyone."
        ),
    ),
    "otp_seller_phone": WhatsAppTemplate(
        name="otp_seller_phone",
        category="AUTHENTICATION",
        variables=("code",),
        render=lambda v: (
            f"Your Khana Bazaar seller verification code is {v['code']}. "
            "It expires in 10 minutes."
        ),
    ),
    "otp_delivery": WhatsAppTemplate(
        name="otp_delivery",
        category="AUTHENTICATION",
        variables=("order_no", "code"),
        render=lambda v: (
            f"Your Khana Bazaar delivery code for order #{v['order_no']} is "
            f"{v['code']}. Share it only with your delivery partner at handover."
        ),
    ),
    "order_placed": WhatsAppTemplate(
        name="order_placed",
        category="UTILITY",
        variables=("order_no", "store"),
        render=lambda v: (
            f"Order #{v['order_no']} placed at {v['store']}. "
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
