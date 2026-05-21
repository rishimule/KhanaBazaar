# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Jinja2-based email rendering.

Templates live in the ``app.email_templates`` package and ship with the wheel.
Loaded via ``PackageLoader`` so they resolve cleanly under Celery prefork.
"""

from dataclasses import dataclass

from jinja2 import (
    Environment,
    PackageLoader,
    StrictUndefined,
    TemplateNotFound,
    select_autoescape,
)

from app.core.config import settings
from app.utils.currency import format_inr


@dataclass(frozen=True)
class EmailPayload:
    subject: str
    preheader: str
    html: str
    text: str


_env = Environment(
    loader=PackageLoader("app", "email_templates"),
    autoescape=select_autoescape(["html"]),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
_env.filters["inr"] = format_inr

_text_env = Environment(
    loader=PackageLoader("app", "email_templates"),
    autoescape=False,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
_text_env.filters["inr"] = format_inr


def _resolve_dir(event: str, lang: str) -> str:
    """Pick `{event}.{lang}` if present, else fall back to `{event}`."""
    if lang and lang != "en":
        try:
            _env.get_template(f"{event}.{lang}/body.html")
            return f"{event}.{lang}"
        except TemplateNotFound:
            pass
    return event


def _global_ctx() -> dict[str, str]:
    return {
        "brand_name": settings.EMAIL_BRAND_NAME,
        "frontend_base_url": settings.EMAIL_FRONTEND_BASE_URL,
        "support_email": settings.SUPPORT_EMAIL,
    }


def render_email(event: str, ctx: dict[str, object], lang: str = "en") -> EmailPayload:
    base_ctx: dict[str, object] = {**_global_ctx(), "lang": lang, **ctx}

    dirname = _resolve_dir(event, lang)
    subject = _text_env.get_template(f"{dirname}/subject.txt").render(base_ctx).strip()
    preheader = (
        _text_env.get_template(f"{dirname}/preheader.txt").render(base_ctx).strip()
    )
    base_ctx["subject"] = subject
    base_ctx["preheader"] = preheader

    html = _env.get_template(f"{dirname}/body.html").render(base_ctx)
    text = _text_env.get_template(f"{dirname}/body.txt").render(base_ctx)

    return EmailPayload(subject=subject, preheader=preheader, html=html, text=text)
