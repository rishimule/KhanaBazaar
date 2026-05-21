# Email Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring Khana Bazaar transactional email to production quality by fixing 10 audited bugs, introducing HTML templates with locale routing, and adding 4 new events (customer welcome, seller-application admin alert, customer-side admin-action notice, post-delivery review request).

**Architecture:** Jinja2 `PackageLoader` for templates shipped inside the `app` Python package. New `core/email_render.py` returns a structured `EmailPayload` (subject/preheader/html/text). Extended `EmailSender.send(to, subject, *, text, html=None, reply_to=None)` posts HTML + text to Resend; console sender mirrors to stdout (and a `/tmp` file in dev). OTP send stays inline at request time and falls back to the rewritten `send_otp_email_async` Celery task on `httpx.HTTPError`. All existing order/seller Celery tasks are rewritten to call `render_email` first, then `get_email_sender().send(...)`. Four new dispatchers wire the new events.

**Tech Stack:** FastAPI, SQLModel, Celery, Redis, Resend (HTTP), Jinja2 (new), pytest.

**Spec:** `docs/superpowers/specs/2026-05-21-email-overhaul-design.md`

---

## File map

**Create:**
- `backend/app/src/app/core/email_render.py`
- `backend/app/src/app/utils/currency.py`
- `backend/app/src/app/email_templates/base.html`
- `backend/app/src/app/email_templates/_partials/button.html`
- `backend/app/src/app/email_templates/_partials/progress_bar.html`
- `backend/app/src/app/email_templates/_partials/line_items.html`
- `backend/app/src/app/email_templates/_partials/footer.html`
- `backend/app/src/app/email_templates/{event}/{subject.txt,preheader.txt,body.html,body.txt}` for 12 events: `otp_login`, `seller_approved`, `seller_rejected`, `seller_application_submitted`, `order_placed_customer`, `order_placed_seller`, `order_status_changed`, `admin_order_action_seller`, `admin_order_action_customer`, `order_review_request`, `customer_welcome`, `support_message`
- `backend/app/tests/test_email_render.py`
- `backend/app/tests/test_currency.py`
- `backend/app/tests/test_customer_welcome_email.py`
- `backend/app/tests/test_seller_application_email.py`
- `backend/app/tests/test_admin_customer_email.py`
- `backend/app/tests/test_order_review_email.py`

**Modify:**
- `backend/app/pyproject.toml` — add `jinja2>=3.1.4`
- `backend/app/src/app/core/email.py` — protocol signature, html/reply_to, dev preview file
- `backend/app/src/app/core/config.py` — `EMAIL_REPLY_TO`, `EMAIL_BRAND_NAME`, `EMAIL_FRONTEND_BASE_URL`, support-email validator
- `backend/app/src/app/worker.py` — rewrite 6 existing tasks + add 4 new tasks + extend `_load_order_email_context`
- `backend/app/src/app/services/order_emails.py` — extend dispatcher signatures + new `admin_order_action_customer` + `order_review_request` fanout
- `backend/app/src/app/services/seller_emails.py` — new `dispatch_seller_application_submitted`, new `dispatch_customer_welcome` (lives here for symmetry with other non-order user-events)
- `backend/app/src/app/api/auth.py` — try/except wrap inline OTP, welcome trigger
- `backend/app/src/app/api/sellers.py` — application-submitted trigger
- `backend/app/src/app/api/customers.py` — pass customer email as reply_to on support send
- `backend/app/tests/test_order_emails.py` — assertions on new dispatchers + signatures

**No DB migration.** No frontend changes.

---

## Conventions used in every task

- Run commands from `backend/app/`.
- After each task: `uv run ruff check . && uv run mypy . && uv run pytest -q` must pass before commit.
- Commits use Conventional Commits; no `Co-Authored-By` trailers.
- Never commit to `main`. Branch already exists from spec phase: `docs/email-overhaul-spec`. Use `feat/email-overhaul` for implementation; the spec stays on its own branch and merges first.

---

## Task 1: Branch + Jinja2 dependency + currency helper

**Files:**
- Create: `backend/app/src/app/utils/currency.py`
- Create: `backend/app/tests/test_currency.py`
- Modify: `backend/app/pyproject.toml`

- [ ] **Step 1: Cut the implementation branch off main (after the spec PR merges)**

```bash
git checkout main && git pull
git checkout -b feat/email-overhaul
```

- [ ] **Step 2: Add Jinja2 to dependencies**

In `backend/app/pyproject.toml`, insert into the `dependencies` list, alphabetically between `httpx` and `meilisearch-python-sdk`:

```toml
    "jinja2>=3.1.4",
```

- [ ] **Step 3: Sync deps**

Run from `backend/app/`:

```bash
uv sync
```

Expected: `Resolved N packages` includes `jinja2`.

- [ ] **Step 4: Write the failing test for `format_inr`**

Create `backend/app/tests/test_currency.py`:

```python
from decimal import Decimal

import pytest

from app.utils.currency import format_inr


@pytest.mark.parametrize(
    "value, expected",
    [
        (0, "₹0.00"),
        (1, "₹1.00"),
        (12.5, "₹12.50"),
        (1234.5, "₹1,234.50"),
        (1234567.89, "₹12,34,567.89"),
        (Decimal("99.99"), "₹99.99"),
        (Decimal("100000"), "₹1,00,000.00"),
    ],
)
def test_format_inr_groups_indian_lakh_crore(value, expected):
    assert format_inr(value) == expected


def test_format_inr_rejects_negative():
    with pytest.raises(ValueError):
        format_inr(-1)
```

- [ ] **Step 5: Run the test, confirm it fails**

```bash
uv run pytest tests/test_currency.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.utils.currency'`.

- [ ] **Step 6: Implement the helper**

Create `backend/app/src/app/utils/currency.py`:

```python
# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Indian Rupee formatting helper.

The Indian numbering convention groups digits as ``xx,xx,xxx.xx`` (lakh/crore),
not ``xxx,xxx.xx``. ``locale.format_string`` is process-global and unsafe in a
server; we group manually.
"""

from decimal import Decimal


def format_inr(value: float | Decimal) -> str:
    if value < 0:
        raise ValueError("format_inr does not support negative values")

    whole = int(value)
    fraction = round(float(value) - whole, 2)
    paise = int(round(fraction * 100))
    if paise == 100:
        whole += 1
        paise = 0

    whole_str = str(whole)
    # Last three digits stand alone; remaining digits group in twos.
    if len(whole_str) <= 3:
        grouped = whole_str
    else:
        head, tail = whole_str[:-3], whole_str[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        grouped = ",".join(groups) + "," + tail

    return f"₹{grouped}.{paise:02d}"
```

- [ ] **Step 7: Run the test, confirm it passes**

```bash
uv run pytest tests/test_currency.py -v
```

Expected: all parametrize cases PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/pyproject.toml backend/app/uv.lock backend/app/src/app/utils/currency.py backend/app/tests/test_currency.py
git commit -m "feat(email): add Jinja2 dep and Indian-format currency helper"
```

---

## Task 2: Settings additions + production support-email validator

**Files:**
- Modify: `backend/app/src/app/core/config.py`
- Test: extend `backend/app/tests/test_jwt.py` is the closest pre-existing config test? No — there is no `test_config.py` yet. Create one.
- Create: `backend/app/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `backend/app/tests/test_config.py`:

```python
import logging
import os

import pytest


def _settings_with(env: dict[str, str]):
    # Reload settings under a controlled env. Import inside the function
    # so the lru_cache on get_email_sender etc. doesn't capture our changes.
    for key, value in env.items():
        os.environ[key] = value
    from importlib import reload

    import app.core.config as config_module

    reload(config_module)
    return config_module.settings


def test_default_email_reply_to_falls_back_to_support_email():
    s = _settings_with({"SUPPORT_EMAIL": "support@khanabazaar.in"})
    assert s.EMAIL_REPLY_TO == "support@khanabazaar.in"


def test_explicit_email_reply_to_overrides_support_email():
    s = _settings_with(
        {"SUPPORT_EMAIL": "support@khanabazaar.in", "EMAIL_REPLY_TO": "noreply@kb.in"}
    )
    assert s.EMAIL_REPLY_TO == "noreply@kb.in"


def test_support_email_example_in_production_emits_warning(caplog):
    caplog.set_level(logging.WARNING)
    _settings_with(
        {"ENVIRONMENT": "production", "SUPPORT_EMAIL": "support@khanabazaar.example"}
    )
    assert any(
        "SUPPORT_EMAIL" in record.message and ".example" in record.message
        for record in caplog.records
    )


def test_brand_name_default():
    s = _settings_with({})
    assert s.EMAIL_BRAND_NAME == "Khana Bazaar"
```

- [ ] **Step 2: Run, confirm fail**

```bash
uv run pytest tests/test_config.py -v
```

Expected: `AttributeError: 'Settings' object has no attribute 'EMAIL_REPLY_TO'`.

- [ ] **Step 3: Extend `Settings`**

In `backend/app/src/app/core/config.py`, add fields and validator (location: alongside the existing email fields). Replace the existing `SUPPORT_EMAIL` line and append:

```python
    SUPPORT_EMAIL: str = "support@khanabazaar.example"
    EMAIL_REPLY_TO: str | None = None  # defaults to SUPPORT_EMAIL at access time
    EMAIL_BRAND_NAME: str = "Khana Bazaar"
    EMAIL_FRONTEND_BASE_URL: str = "http://localhost:3000"
```

After the field declarations but inside the class body, append a `model_validator`:

```python
    @model_validator(mode="after")
    def _resolve_email_defaults(self) -> "Settings":
        if self.EMAIL_REPLY_TO is None:
            object.__setattr__(self, "EMAIL_REPLY_TO", self.SUPPORT_EMAIL)
        if self.ENVIRONMENT == "production" and ".example" in self.SUPPORT_EMAIL:
            import logging

            logging.getLogger(__name__).warning(
                "SUPPORT_EMAIL still uses the .example placeholder in production: %s",
                self.SUPPORT_EMAIL,
            )
        return self
```

Also add `from pydantic import model_validator` at the top of the file if not already imported.

- [ ] **Step 4: Run config test**

```bash
uv run pytest tests/test_config.py -v
```

Expected: all 4 PASS.

- [ ] **Step 5: Run the whole test suite to confirm no regressions**

```bash
uv run pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/core/config.py backend/app/tests/test_config.py
git commit -m "feat(email): config knobs and production placeholder-email validator"
```

---

## Task 3: Extend EmailSender protocol with html/reply_to + dev preview

**Files:**
- Modify: `backend/app/src/app/core/email.py`
- Modify: `backend/app/src/app/api/auth.py` (call sites)
- Create: `backend/app/tests/test_email_sender.py`

- [ ] **Step 1: Write the failing test**

Create `backend/app/tests/test_email_sender.py`:

```python
import asyncio
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from app.core.email import (
    ConsoleEmailSender,
    EmailSender,
    ResendEmailSender,
    get_email_sender,
)


def test_console_sender_accepts_html_and_text_kwargs():
    sender = ConsoleEmailSender()
    asyncio.run(
        sender.send(
            to="x@example.com",
            subject="hello",
            text="hi",
            html="<p>hi</p>",
            reply_to="rep@example.com",
        )
    )


def test_console_sender_writes_dev_preview_file_when_html_present(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.email._DEV_PREVIEW_DIR", str(tmp_path))
    sender = ConsoleEmailSender()
    asyncio.run(
        sender.send(
            to="x@example.com",
            subject="Preview Test Email",
            text="hi",
            html="<p>hi</p>",
        )
    )
    files = list(Path(tmp_path).glob("khanabazaar_email_*.html"))
    assert len(files) == 1
    assert "<p>hi</p>" in files[0].read_text()


def test_console_sender_skips_preview_when_html_none(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.email._DEV_PREVIEW_DIR", str(tmp_path))
    sender = ConsoleEmailSender()
    asyncio.run(sender.send(to="x@example.com", subject="text only", text="hi"))
    assert list(Path(tmp_path).glob("*.html")) == []


@respx.mock
def test_resend_sender_posts_html_text_and_reply_to():
    route = respx.post("https://api.resend.com/emails").mock(
        return_value=httpx.Response(200, json={"id": "fake"})
    )
    sender = ResendEmailSender()
    asyncio.run(
        sender.send(
            to="x@example.com",
            subject="hello",
            text="hi",
            html="<p>hi</p>",
            reply_to="rep@example.com",
        )
    )
    assert route.called
    payload = route.calls.last.request.content
    assert b'"html":"<p>hi</p>"' in payload
    assert b'"text":"hi"' in payload
    assert b'"reply_to":"rep@example.com"' in payload
```

Add `respx>=0.21.0` to the dev-dependencies group in `pyproject.toml`:

```toml
dev = [
    "aiosqlite>=0.22.1",
    "fakeredis>=2.25.0",
    "mypy>=1.19.1",
    "pytest>=9.0.2",
    "pytest-asyncio>=1.3.0",
    "pytest-cov>=7.0.0",
    "respx>=0.21.0",
    "ruff>=0.15.5",
]
```

Run `uv sync`.

- [ ] **Step 2: Run, confirm fail**

```bash
uv run pytest tests/test_email_sender.py -v
```

Expected: TypeError on the new kwargs (`send()` got an unexpected keyword argument 'html').

- [ ] **Step 3: Update `core/email.py`**

Replace the file contents with:

```python
# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import json
import logging
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_DEV_PREVIEW_DIR = "/tmp"
_SUBJECT_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _SUBJECT_SLUG_RE.sub("-", text.lower()).strip("-")[:60] or "email"


class EmailSender(Protocol):
    async def send(
        self,
        to: str,
        subject: str,
        *,
        text: str,
        html: str | None = None,
        reply_to: str | None = None,
    ) -> None: ...


class ConsoleEmailSender:
    async def send(
        self,
        to: str,
        subject: str,
        *,
        text: str,
        html: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        logger.info(
            "[EMAIL] to=%s reply_to=%s subject=%r\n%s",
            to,
            reply_to,
            subject,
            text,
        )
        print(f"[EMAIL] to={to}\n{text}")
        if html and _DEV_PREVIEW_DIR:
            try:
                path = Path(_DEV_PREVIEW_DIR) / (
                    f"khanabazaar_email_{_slug(subject)}_{int(time.time() * 1000)}.html"
                )
                path.write_text(html, encoding="utf-8")
                logger.info("[EMAIL] dev preview written: %s", path)
            except OSError as exc:
                logger.debug("dev preview write failed: %s", exc)


class ResendEmailSender:
    async def send(
        self,
        to: str,
        subject: str,
        *,
        text: str,
        html: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "text": text,
        }
        if html is not None:
            payload["html"] = html
        if reply_to is not None:
            payload["reply_to"] = reply_to
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                content=json.dumps(payload),
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()


class ResendWithConsoleSender:
    def __init__(self) -> None:
        self._console = ConsoleEmailSender()
        self._resend = ResendEmailSender()

    async def send(
        self,
        to: str,
        subject: str,
        *,
        text: str,
        html: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        await self._console.send(
            to, subject, text=text, html=html, reply_to=reply_to
        )
        try:
            await self._resend.send(
                to, subject, text=text, html=html, reply_to=reply_to
            )
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "[EMAIL] Resend rejected to=%s status=%s body=%s (console fallback already logged)",
                to,
                exc.response.status_code,
                exc.response.text,
            )


@lru_cache(maxsize=1)
def get_email_sender() -> EmailSender:
    if settings.EMAIL_PROVIDER == "resend":
        return ResendEmailSender()
    if settings.EMAIL_PROVIDER == "resend+console":
        return ResendWithConsoleSender()
    return ConsoleEmailSender()
```

- [ ] **Step 4: Update `api/auth.py` call site at line ~103**

Replace the inline OTP send (no HTML yet — Task 7 wires the template; for now, just keep it text-only but using the new kwarg form):

```python
    await sender.send(
        to=email,
        subject="Your Khana Bazaar login code",
        text=f"Your one-time login code is: {code}\n\nThis code expires in 10 minutes.",
    )
```

(Stays text-only for the moment; Task 7 swaps in the rendered template.)

- [ ] **Step 5: Run the email-sender tests**

```bash
uv run pytest tests/test_email_sender.py -v
```

Expected: 4 PASS.

- [ ] **Step 6: Run full suite**

```bash
uv run pytest -q
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add backend/app/pyproject.toml backend/app/uv.lock backend/app/src/app/core/email.py backend/app/src/app/api/auth.py backend/app/tests/test_email_sender.py
git commit -m "feat(email): EmailSender protocol takes html and reply_to; dev HTML preview"
```

---

## Task 4: Scaffold `email_templates` package + base layout + partials

**Files:**
- Create: `backend/app/src/app/email_templates/__init__.py` (empty)
- Create: `backend/app/src/app/email_templates/base.html`
- Create: `backend/app/src/app/email_templates/_partials/{button,progress_bar,line_items,footer}.html`

- [ ] **Step 1: Create the package marker**

```bash
mkdir -p backend/app/src/app/email_templates/_partials
touch backend/app/src/app/email_templates/__init__.py
touch backend/app/src/app/email_templates/_partials/__init__.py
```

- [ ] **Step 2: Write `base.html`**

Create `backend/app/src/app/email_templates/base.html`:

```html
<!doctype html>
<html lang="{{ lang|default('en') }}">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{{ subject }}</title>
  </head>
  <body style="margin:0;padding:0;background:#f6f7f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1f2937;">
    <div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">
      {{ preheader }}&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;
    </div>
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f6f7f9;padding:24px 0;">
      <tr>
        <td align="center">
          <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;background:#ffffff;border-radius:8px;overflow:hidden;">
            <tr>
              <td style="padding:24px 32px;background:#0b8457;color:#ffffff;">
                <div style="font-size:20px;font-weight:700;letter-spacing:0.5px;">{{ brand_name }}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:32px;font-size:16px;line-height:1.55;">
                {% block body %}{% endblock %}
              </td>
            </tr>
            {% include "_partials/footer.html" %}
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
```

- [ ] **Step 3: Write `_partials/button.html`**

Create `backend/app/src/app/email_templates/_partials/button.html`:

```html
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0;">
  <tr>
    <td style="background:#0b8457;border-radius:6px;">
      <a href="{{ cta_url }}" style="display:inline-block;padding:12px 24px;color:#ffffff;text-decoration:none;font-weight:600;font-size:15px;">
        {{ cta_label }}
      </a>
    </td>
  </tr>
</table>
```

- [ ] **Step 4: Write `_partials/progress_bar.html`**

Create `backend/app/src/app/email_templates/_partials/progress_bar.html`:

```html
{# Renders four pills: pending → packed → dispatched → delivered.
   `current` is the active status string. `cancelled` renders all greyed with a red badge. #}
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:16px 0 24px;">
  <tr>
    {% set steps = ['pending', 'packed', 'dispatched', 'delivered'] %}
    {% set current_idx = steps.index(current) if current in steps else -1 %}
    {% for step in steps %}
      {% set reached = loop.index0 <= current_idx %}
      <td align="center" style="padding:4px;">
        <div style="
          width:24px;height:24px;border-radius:50%;
          background:{{ '#0b8457' if reached else '#d1d5db' }};
          margin:0 auto 6px;"></div>
        <div style="font-size:12px;color:{{ '#0b8457' if reached else '#9ca3af' }};text-transform:capitalize;">
          {{ step }}
        </div>
      </td>
    {% endfor %}
  </tr>
  {% if current == 'cancelled' %}
    <tr>
      <td colspan="4" align="center" style="padding-top:8px;color:#b91c1c;font-weight:600;">
        Cancelled
      </td>
    </tr>
  {% endif %}
</table>
```

(Note: Jinja's `steps.index(current)` is a list method, available via `do` extension or just `loop`-based fallback. To stay safe with default Jinja, swap the index calc into Python via a context var. Apply the change in Task 6 if `index` is unavailable — for now this template will be tested with `current='packed'` etc. Replace the line `{% set current_idx = steps.index(current) if current in steps else -1 %}` with: `{% set current_idx = {'pending':0,'packed':1,'dispatched':2,'delivered':3}.get(current, -1) %}`)

- [ ] **Step 5: Write `_partials/line_items.html`**

Create `backend/app/src/app/email_templates/_partials/line_items.html`:

```html
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;margin:16px 0;">
  <thead>
    <tr style="border-bottom:1px solid #e5e7eb;">
      <th align="left" style="padding:8px 0;font-size:13px;color:#6b7280;font-weight:500;">Item</th>
      <th align="center" style="padding:8px 0;font-size:13px;color:#6b7280;font-weight:500;">Qty</th>
      <th align="right" style="padding:8px 0;font-size:13px;color:#6b7280;font-weight:500;">Total</th>
    </tr>
  </thead>
  <tbody>
    {% for item in items %}
      <tr style="border-bottom:1px solid #f3f4f6;">
        <td style="padding:8px 0;font-size:15px;">{{ item.name }}</td>
        <td align="center" style="padding:8px 0;font-size:15px;">{{ item.qty }}</td>
        <td align="right" style="padding:8px 0;font-size:15px;">{{ item.line_total|inr }}</td>
      </tr>
    {% endfor %}
    <tr>
      <td colspan="2" align="right" style="padding:12px 8px 0;font-size:15px;font-weight:600;">Total</td>
      <td align="right" style="padding:12px 0 0;font-size:15px;font-weight:700;">{{ order_total|inr }}</td>
    </tr>
  </tbody>
</table>
```

- [ ] **Step 6: Write `_partials/footer.html`**

Create `backend/app/src/app/email_templates/_partials/footer.html`:

```html
<tr>
  <td style="padding:24px 32px;background:#f9fafb;color:#6b7280;font-size:12px;line-height:1.5;text-align:center;">
    Sent by {{ brand_name }}. Reply to this email or write to
    <a href="mailto:{{ support_email }}" style="color:#0b8457;">{{ support_email }}</a>.
    <br>
    {{ brand_name }} — multi-vendor hyperlocal commerce, India.
  </td>
</tr>
```

- [ ] **Step 7: Commit (no tests yet — partials are exercised in Task 5)**

```bash
git add backend/app/src/app/email_templates/
git commit -m "feat(email): base HTML layout, button/progress/line-items/footer partials"
```

---

## Task 5: `core/email_render.py` — Jinja env, render_email, EmailPayload + tests

**Files:**
- Create: `backend/app/src/app/core/email_render.py`
- Create: `backend/app/tests/test_email_render.py`
- Create: minimal smoke template `backend/app/src/app/email_templates/_smoke/{subject.txt,preheader.txt,body.html,body.txt}` for the test

- [ ] **Step 1: Add the smoke template (used only by tests)**

Create `backend/app/src/app/email_templates/_smoke/subject.txt`:

```
[Khana Bazaar] Smoke {{ name }}
```

Create `backend/app/src/app/email_templates/_smoke/preheader.txt`:

```
preheader for {{ name }}
```

Create `backend/app/src/app/email_templates/_smoke/body.html`:

```html
{% extends "base.html" %}
{% block body %}
  <p>Hello {{ name }}, your total is {{ total|inr }}.</p>
  {% set cta_url = frontend_base_url ~ "/x" %}
  {% set cta_label = "Click" %}
  {% include "_partials/button.html" %}
{% endblock %}
```

Create `backend/app/src/app/email_templates/_smoke/body.txt`:

```
Hello {{ name }}, your total is {{ total|inr }}.
Click: {{ frontend_base_url }}/x
```

- [ ] **Step 2: Write the failing test**

Create `backend/app/tests/test_email_render.py`:

```python
import pytest
from jinja2 import UndefinedError

from app.core.email_render import EmailPayload, render_email


def test_render_email_returns_subject_preheader_html_text():
    payload = render_email("_smoke", {"name": "Ravi", "total": 1234.5}, lang="en")
    assert isinstance(payload, EmailPayload)
    assert payload.subject == "[Khana Bazaar] Smoke Ravi"
    assert payload.preheader == "preheader for Ravi"
    assert "Hello Ravi" in payload.html
    assert "₹1,234.50" in payload.html
    assert "Hello Ravi" in payload.text
    assert "Khana Bazaar" in payload.html  # brand_name auto-injected
    # No raw Jinja markers in output
    assert "{{ " not in payload.html
    assert "{{ " not in payload.text


def test_render_email_raises_on_missing_required_var():
    with pytest.raises(UndefinedError):
        render_email("_smoke", {"total": 0}, lang="en")  # no `name`


def test_render_email_falls_back_to_default_lang_when_locale_dir_missing():
    # _smoke has no _smoke.hi dir; should still render via the base.
    payload = render_email("_smoke", {"name": "A", "total": 0}, lang="hi")
    assert "Hello A" in payload.html
```

- [ ] **Step 3: Run, confirm fail**

```bash
uv run pytest tests/test_email_render.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.core.email_render'`.

- [ ] **Step 4: Implement the render module**

Create `backend/app/src/app/core/email_render.py`:

```python
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
```

- [ ] **Step 5: Run the render test**

```bash
uv run pytest tests/test_email_render.py -v
```

Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/core/email_render.py backend/app/src/app/email_templates/_smoke/ backend/app/tests/test_email_render.py
git commit -m "feat(email): Jinja2 render_email() with EmailPayload, StrictUndefined, locale fallback"
```

---

## Task 6: Extend `_load_order_email_context` with items, first_name, lang

**Files:**
- Modify: `backend/app/src/app/worker.py` (replace `_load_order_email_context`)
- Modify: `backend/app/tests/test_order_emails.py` (extend existing test that exercises the loader)

- [ ] **Step 1: Write the failing test**

Open `backend/app/tests/test_order_emails.py`, locate the existing `_make_order_for_email_tests` (or equivalent helper used by `test_placed_seller_email_includes_service_name`). Re-use it. Add this test after the existing ones:

```python
import pytest

from app.worker import _load_order_email_context


@pytest.mark.asyncio
async def test_loader_returns_items_and_first_name(async_session):
    # Reuse the helper that the existing tests use to build a complete
    # order/customer/store graph. The helper must also create 2 OrderItems.
    order = await _make_order_for_email_tests(
        async_session,
        items=[
            {"name": "Apple", "qty": 2, "unit_price": 50.0, "line_total": 100.0},
            {"name": "Banana", "qty": 1, "unit_price": 30.0, "line_total": 30.0},
        ],
        customer_first_name="Ravi",
    )

    ctx = _load_order_email_context(order.id)

    assert ctx["items"] == [
        {"name": "Apple", "qty": 2, "unit_price": 50.0, "line_total": 100.0},
        {"name": "Banana", "qty": 1, "unit_price": 30.0, "line_total": 30.0},
    ]
    assert ctx["customer_first_name"] == "Ravi"
    assert ctx["customer_lang"] == "en"
    assert ctx["seller_lang"] == "en"
    assert "delivery_address_snapshot" in ctx
```

If `_make_order_for_email_tests` does not exist yet (the existing tests may inline their setup), extract it into a fixture/helper as part of this step. Mirror the inline construction in `test_placed_seller_email_includes_service_name` and accept `items: list[dict]` and `customer_first_name: str` as kwargs. Place the helper at the top of the test file so all tests can share it.

- [ ] **Step 2: Run, confirm the new assertions fail**

```bash
uv run pytest tests/test_order_emails.py::test_loader_returns_items_and_first_name -v
```

Expected: `KeyError: 'items'`.

- [ ] **Step 3: Extend the loader in `worker.py`**

Inside `_load_order_email_context._load`, after the existing `customer_user` load, additionally fetch:

```python
                from app.models.commerce import OrderItem

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
                customer_first_name = (
                    customer_profile.first_name if customer_profile else None
                )
                customer_lang = (
                    customer_user.preferred_language if customer_user else "en"
                )
                seller_lang = (
                    seller_user.preferred_language if seller_user else "en"
                )
```

Add these to the returned dict:

```python
                return {
                    "order_id": order.id,
                    "order_total": order.total,
                    "order_status": order.status.value,
                    "service_name": order.service_name_snapshot,
                    "store_name": store.name if store is not None else None,
                    "seller_email": seller_user.email if seller_user is not None else None,
                    "customer_email": customer_user.email if customer_user is not None else None,
                    "items": items,
                    "customer_first_name": customer_first_name,
                    "customer_lang": customer_lang,
                    "seller_lang": seller_lang,
                    "delivery_address_snapshot": order.delivery_address_snapshot,
                }
```

- [ ] **Step 4: Run the test, confirm pass**

```bash
uv run pytest tests/test_order_emails.py::test_loader_returns_items_and_first_name -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite to confirm no regressions in existing tests**

```bash
uv run pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/src/app/worker.py backend/app/tests/test_order_emails.py
git commit -m "feat(email): loader returns order items, customer first name, locales"
```

---

## Task 7: `otp_login` template + rewrite `send_otp_email_async` + inline fallback wiring

**Files:**
- Create: `backend/app/src/app/email_templates/otp_login/{subject.txt,preheader.txt,body.html,body.txt}`
- Modify: `backend/app/src/app/worker.py` (`send_otp_email_async` rewrite)
- Modify: `backend/app/src/app/api/auth.py` (`otp_request` handler — switch to rendered template + httpx-error fallback to Celery)
- Test: extend `backend/app/tests/test_otp.py` (new test for fallback enqueue)

- [ ] **Step 1: Write the template files**

`otp_login/subject.txt`:

```
[{{ brand_name }}] Your login code
```

`otp_login/preheader.txt`:

```
Your one-time code: {{ code }} (expires in {{ ttl_minutes }} min).
```

`otp_login/body.html`:

```html
{% extends "base.html" %}
{% block body %}
  <p>Hi,</p>
  <p>Your one-time login code is:</p>
  <p style="font-size:28px;font-weight:700;letter-spacing:4px;background:#f3f4f6;padding:16px 24px;border-radius:6px;text-align:center;">
    {{ code }}
  </p>
  <p style="color:#6b7280;font-size:14px;">This code expires in {{ ttl_minutes }} minutes. If you did not request it, ignore this email.</p>
{% endblock %}
```

`otp_login/body.txt`:

```
Your {{ brand_name }} login code: {{ code }}

This code expires in {{ ttl_minutes }} minutes.
If you did not request it, ignore this email.
```

- [ ] **Step 2: Write the failing test for fallback enqueue**

Append to `backend/app/tests/test_otp.py`:

```python
import httpx
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_inline_otp_fallback_enqueues_celery_on_httperror(client, monkeypatch):
    # Force the sender to raise an httpx error; assert Celery task was enqueued
    # with the same (email, code).
    enqueue = AsyncMock()
    failing_send = AsyncMock(side_effect=httpx.ConnectError("boom"))

    with patch("app.core.email.ResendEmailSender.send", new=failing_send), \
         patch("app.worker.send_otp_email_async.delay", new=enqueue):
        resp = await client.post(
            "/api/v1/auth/otp/request", json={"email": "x@example.com"}
        )
    assert resp.status_code == 200
    assert enqueue.called
    assert enqueue.call_args.args[0] == "x@example.com"
```

(Add a fixture to set `EMAIL_PROVIDER=resend` for this test if your test env defaults to console.)

- [ ] **Step 3: Run, confirm fail**

```bash
uv run pytest tests/test_otp.py::test_inline_otp_fallback_enqueues_celery_on_httperror -v
```

Expected: failure — either the path doesn't catch the error or `send_otp_email_async` is not invoked.

- [ ] **Step 4: Wire the inline fallback in `api/auth.py`**

In `otp_request` (around line 95-108), replace the inline send block:

```python
    from app.core.email_render import render_email
    from app.worker import send_otp_email_async

    ttl_minutes = settings.OTP_TTL_SECONDS // 60
    payload = render_email("otp_login", {"code": code, "ttl_minutes": ttl_minutes}, lang="en")
    try:
        await sender.send(
            to=email,
            subject=payload.subject,
            text=payload.text,
            html=payload.html,
            reply_to=settings.EMAIL_REPLY_TO,
        )
    except httpx.HTTPError:
        send_otp_email_async.delay(email, code)
```

(Import `httpx` at the top of the file if not already imported.)

- [ ] **Step 5: Rewrite `send_otp_email_async` in `worker.py`**

Replace lines 18-38 of `worker.py`:

```python
@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_otp_email_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_otp_email_async(to: str, code: str) -> None:
    """Render the otp_login template and dispatch. Fallback path for inline send failures."""
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
```

Update `_resolve_email` signature to match:

```python
def _resolve_email(
    to: str,
    subject: str,
    body: str,
    *,
    html: str | None = None,
    reply_to: str | None = None,
) -> None:
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
```

- [ ] **Step 6: Run the test**

```bash
uv run pytest tests/test_otp.py -v
```

Expected: all PASS.

- [ ] **Step 7: Run full suite**

```bash
uv run pytest -q
```

Expected: green.

- [ ] **Step 8: Commit**

```bash
git add backend/app/src/app/email_templates/otp_login/ backend/app/src/app/worker.py backend/app/src/app/api/auth.py backend/app/tests/test_otp.py
git commit -m "feat(email): otp_login HTML template + inline-with-Celery-fallback delivery"
```

---

## Tasks 8 – 18: Per-event template + worker-task rewrite

Each follows the same TDD micro-shape as Task 7 (write failing test, confirm fail, implement, confirm pass, commit). The deltas below give the exact template content and Python signature changes. The TDD step ordering is identical to Task 7 and is not repeated.

### Task 8: `seller_approved`

**Create `backend/app/src/app/email_templates/seller_approved/subject.txt`:**

```
[{{ brand_name }}] Your seller application is approved
```

**Create `seller_approved/preheader.txt`:**

```
You can now manage your store inventory and accept orders.
```

**Create `seller_approved/body.html`:**

```html
{% extends "base.html" %}
{% block body %}
  <p>Congratulations,</p>
  <p>Your seller application for <strong>{{ business_name }}</strong> is approved. You can now manage your inventory, set prices, and accept orders.</p>
  {% set cta_url = frontend_base_url ~ "/seller" %}
  {% set cta_label = "Open seller dashboard" %}
  {% include "_partials/button.html" %}
  <p style="color:#6b7280;font-size:14px;">Need help? Reply to this email or write to <a href="mailto:{{ support_email }}" style="color:#0b8457;">{{ support_email }}</a>.</p>
{% endblock %}
```

**Create `seller_approved/body.txt`:**

```
Congratulations!

Your seller application for {{ business_name }} is approved.

Open your seller dashboard:
{{ frontend_base_url }}/seller

Need help? Reply to this email or write to {{ support_email }}.
```

**Rewrite `send_seller_approved_async` in `worker.py`:**

```python
@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_seller_approved_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_seller_approved_async(to_email: str, business_name: str) -> None:
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
```

**Test (extend `tests/test_seller_register.py` or `tests/test_admin_applications.py` — whichever currently exercises the approval flow):**

```python
def test_seller_approved_email_renders_dashboard_cta(monkeypatch):
    captured = {}

    def fake_resolve(to, subject, body, *, html=None, reply_to=None):
        captured["to"] = to
        captured["subject"] = subject
        captured["html"] = html

    monkeypatch.setattr("app.worker._resolve_email", fake_resolve)
    from app.worker import send_seller_approved_async

    send_seller_approved_async("seller@example.com", "Sample Mart")

    assert captured["to"] == "seller@example.com"
    assert "[Khana Bazaar]" in captured["subject"]
    assert "approved" in captured["subject"].lower()
    assert "/seller" in captured["html"]
    assert "Sample Mart" in captured["html"]
```

**Commit:** `feat(email): seller_approved HTML template`.

### Task 9: `seller_rejected`

**Create `seller_rejected/subject.txt`:**

```
[{{ brand_name }}] Update on your seller application
```

**Create `seller_rejected/preheader.txt`:**

```
Your application was not approved. Reason: {{ reason|default('See email for details') }}.
```

**Create `seller_rejected/body.html`:**

```html
{% extends "base.html" %}
{% block body %}
  <p>Hi,</p>
  <p>Your seller application for <strong>{{ business_name }}</strong> was not approved at this time.</p>
  <div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:12px 16px;margin:16px 0;border-radius:4px;">
    <div style="font-size:13px;color:#78350f;font-weight:600;margin-bottom:4px;">Reason</div>
    <div style="font-size:15px;color:#1f2937;">{{ reason }}</div>
  </div>
  <p>You can update your application and resubmit for review.</p>
  {% set cta_url = frontend_base_url ~ "/seller/signup" %}
  {% set cta_label = "Update application" %}
  {% include "_partials/button.html" %}
{% endblock %}
```

**Create `seller_rejected/body.txt`:**

```
Hi,

Your seller application for {{ business_name }} was not approved at this time.

Reason: {{ reason }}

You can update and resubmit:
{{ frontend_base_url }}/seller/signup
```

**Rewrite `send_seller_rejected_async`:**

```python
@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_seller_rejected_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_seller_rejected_async(to_email: str, business_name: str, reason: str) -> None:
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
```

**Test:** same shape as Task 8 test; assert `"Documents missing"` (the reason) and `/seller/signup` (the CTA URL) both appear in `captured["html"]`.

**Commit:** `feat(email): seller_rejected HTML template`.

### Task 10: `seller_application_submitted` (NEW event)

**Create `seller_application_submitted/subject.txt`:**

```
[{{ brand_name }}] New seller application: {{ business_name }}
```

**Create `seller_application_submitted/preheader.txt`:**

```
{{ applicant_email }} submitted at {{ submitted_at }}.
```

**Create `seller_application_submitted/body.html`:**

```html
{% extends "base.html" %}
{% block body %}
  <p>A new seller application is pending review.</p>
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:16px 0;">
    <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;width:140px;">Business name</td><td style="padding:6px 0;font-size:15px;font-weight:600;">{{ business_name }}</td></tr>
    <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">Applicant email</td><td style="padding:6px 0;font-size:15px;">{{ applicant_email }}</td></tr>
    <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">Submitted at</td><td style="padding:6px 0;font-size:15px;">{{ submitted_at }}</td></tr>
  </table>
  {% set cta_url = frontend_base_url ~ "/admin/sellers" %}
  {% set cta_label = "Review applications" %}
  {% include "_partials/button.html" %}
{% endblock %}
```

**Create `seller_application_submitted/body.txt`:**

```
New seller application is pending review.

Business name : {{ business_name }}
Applicant     : {{ applicant_email }}
Submitted at  : {{ submitted_at }}

Review queue: {{ frontend_base_url }}/admin/sellers
```

**New worker task in `worker.py`:**

```python
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
                return {
                    "business_name": profile.business_name,
                    "applicant_email": user.email if user else "",
                    "submitted_at": profile.updated_at.strftime("%Y-%m-%d %H:%M UTC")
                    if hasattr(profile, "updated_at") and profile.updated_at
                    else "",
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
```

**New dispatcher in `services/seller_emails.py`:**

```python
def dispatch_seller_application_submitted(seller_profile_id: int) -> None:
    from app.worker import send_seller_application_submitted_async

    _safe_delay(send_seller_application_submitted_async, seller_profile_id)
```

**Trigger:** in `api/sellers.py`, in the register handler and the resubmit handler, immediately after `await session.commit()` (and `await session.refresh(profile)` if present) and only when `profile.verification_status == VerificationStatus.Pending`, call:

```python
    if profile.verification_status == VerificationStatus.Pending and profile.id is not None:
        dispatch_seller_application_submitted(profile.id)
```

(Import `dispatch_seller_application_submitted` at the top of `api/sellers.py`.)

**Test (`tests/test_seller_application_email.py`):**

```python
import pytest


@pytest.mark.asyncio
async def test_register_dispatches_application_submitted(monkeypatch, ...):
    enqueued = []

    def fake_delay(*args, **_kwargs):
        enqueued.append(args)

    from app.worker import send_seller_application_submitted_async

    monkeypatch.setattr(send_seller_application_submitted_async, "delay", fake_delay)

    # Drive the seller-register endpoint with a fresh user; use the test patterns
    # already present in tests/test_seller_register.py for header/body shape.
    # ...register seller...

    assert len(enqueued) == 1
```

Build out the `...` blocks by copying the request fixture from `tests/test_seller_register.py`.

**Commit:** `feat(email): seller_application_submitted alert to support inbox`.

### Task 11: `order_placed_customer` (line items, CTA)

**Create `order_placed_customer/subject.txt`:**

```
{% if orders|length == 1 -%}
[{{ brand_name }}] Order #{{ orders[0].order_id }} confirmed
{%- else -%}
[{{ brand_name }}] {{ orders|length }} orders confirmed
{%- endif %}
```

**Create `order_placed_customer/preheader.txt`:**

```
{% if orders|length == 1 -%}
{{ orders[0].store_name }} · {{ orders[0].service_name }} · {{ orders[0].order_total|inr }}
{%- else -%}
You placed {{ orders|length }} orders. Total {{ grand_total|inr }}.
{%- endif %}
```

**Create `order_placed_customer/body.html`:**

```html
{% extends "base.html" %}
{% block body %}
  <p>Hi {{ customer_first_name|default('there') }},</p>
  <p>Thanks for shopping with {{ brand_name }}. Here {{ 'is' if orders|length == 1 else 'are' }} your order details:</p>

  {% for o in orders %}
    <div style="margin-top:24px;padding:16px;border:1px solid #e5e7eb;border-radius:8px;">
      <div style="font-size:16px;font-weight:600;">Order #{{ o.order_id }} — {{ o.service_name }}</div>
      <div style="font-size:14px;color:#6b7280;margin-bottom:8px;">{{ o.store_name }}</div>
      {% with items=o.items, order_total=o.order_total %}
        {% include "_partials/line_items.html" %}
      {% endwith %}
    </div>
  {% endfor %}

  {% if orders|length == 1 %}
    {% set cta_url = frontend_base_url ~ "/account/orders/" ~ orders[0].order_id|string %}
    {% set cta_label = "View order" %}
  {% else %}
    {% set cta_url = frontend_base_url ~ "/account/orders" %}
    {% set cta_label = "View all orders" %}
  {% endif %}
  {% include "_partials/button.html" %}

  <p style="color:#6b7280;font-size:14px;">We will email you again when your {{ 'order is' if orders|length == 1 else 'orders are' }} packed and on the way.</p>
{% endblock %}
```

**Create `order_placed_customer/body.txt`:**

```
Hi {{ customer_first_name|default('there') }},

Thanks for shopping with {{ brand_name }}.

{% for o in orders -%}
Order #{{ o.order_id }} — {{ o.service_name }} ({{ o.store_name }})
{% for item in o.items -%}
  - {{ item.name }} × {{ item.qty }} = {{ item.line_total|inr }}
{% endfor -%}
Total: {{ o.order_total|inr }}

{% endfor -%}
{% if orders|length == 1 -%}
View order: {{ frontend_base_url }}/account/orders/{{ orders[0].order_id }}
{%- else -%}
View all orders: {{ frontend_base_url }}/account/orders
{%- endif %}
```

**Rewrite `send_order_confirmed_customer_async`:**

```python
@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_order_confirmed_customer_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_order_confirmed_customer_async(order_ids: list[int]) -> None:
    from app.core.config import settings
    from app.core.email_render import render_email

    customer_email: str | None = None
    customer_first_name: str | None = None
    customer_lang = "en"
    orders: list[dict[str, Any]] = []
    grand_total = 0.0

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
                "items": ctx["items"],
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
```

**Test (extend `test_order_emails.py::test_confirmed_customer_email_includes_service_name`):** in the patched `_resolve_email`, capture `html`. Assert it contains item names, `₹`, and `/account/orders/{order_id}`.

**Commit:** `feat(email): order_placed_customer HTML template with line items and CTA`.

### Task 12: `order_placed_seller`

**Create `order_placed_seller/subject.txt`:**

```
[{{ brand_name }}] New {{ service_name }} order #{{ order_id }}
```

**Create `order_placed_seller/preheader.txt`:**

```
{{ items|length }} item(s) — total {{ order_total|inr }}. Prepare for packing.
```

**Create `order_placed_seller/body.html`:**

```html
{% extends "base.html" %}
{% block body %}
  <p>You have a new <strong>{{ service_name }}</strong> order at <strong>{{ store_name }}</strong>.</p>
  <div style="font-size:18px;font-weight:700;margin:8px 0;">Order #{{ order_id }}</div>
  {% include "_partials/line_items.html" %}
  {% set cta_url = frontend_base_url ~ "/seller/orders/" ~ order_id|string %}
  {% set cta_label = "Open order" %}
  {% include "_partials/button.html" %}
{% endblock %}
```

**Create `order_placed_seller/body.txt`:**

```
You have a new {{ service_name }} order at {{ store_name }}.

Order #{{ order_id }}
{% for item in items -%}
  - {{ item.name }} × {{ item.qty }} = {{ item.line_total|inr }}
{% endfor %}
Total: {{ order_total|inr }}

Open order: {{ frontend_base_url }}/seller/orders/{{ order_id }}
```

**Rewrite `send_order_placed_seller_async`:**

```python
@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_order_placed_seller_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_order_placed_seller_async(order_id: int) -> None:
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
            "items": ctx["items"],
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
```

**Test (extend `test_order_emails.py::test_placed_seller_email_includes_service_name`):** capture html and assert `Open order`, `/seller/orders/`, and at least one item name appear.

**Commit:** `feat(email): order_placed_seller HTML template`.

### Task 13: `order_status_changed` (progress bar + cancel reason)

**Create `order_status_changed/subject.txt`:**

```
[{{ brand_name }}] Order #{{ order_id }} is now {{ current }}
```

**Create `order_status_changed/preheader.txt`:**

```
{{ service_name }} order at {{ store_name }}.
```

**Create `order_status_changed/body.html`:**

```html
{% extends "base.html" %}
{% block body %}
  <p>Order <strong>#{{ order_id }}</strong> — {{ service_name }} at {{ store_name }} — is now <strong style="text-transform:capitalize;">{{ current }}</strong>.</p>
  {% include "_partials/progress_bar.html" %}
  {% if current == 'cancelled' and reason %}
    <div style="background:#fef2f2;border-left:4px solid #b91c1c;padding:12px 16px;margin:16px 0;border-radius:4px;">
      <div style="font-size:13px;color:#7f1d1d;font-weight:600;margin-bottom:4px;">Cancellation reason</div>
      <div style="font-size:15px;color:#1f2937;">{{ reason }}</div>
    </div>
  {% endif %}
  {% set cta_url = frontend_base_url ~ ("/seller/orders/" if recipient == 'seller' else "/account/orders/") ~ order_id|string %}
  {% set cta_label = "View order" %}
  {% include "_partials/button.html" %}
{% endblock %}
```

**Create `order_status_changed/body.txt`:**

```
Order #{{ order_id }} — {{ service_name }} at {{ store_name }} — is now {{ current }}.

{% if current == 'cancelled' and reason -%}
Cancellation reason: {{ reason }}
{% endif -%}

View order: {{ frontend_base_url }}{{ '/seller/orders/' if recipient == 'seller' else '/account/orders/' }}{{ order_id }}
```

**Rewrite `send_order_status_changed_async`:**

```python
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
    from app.core.config import settings
    from app.core.email_render import render_email

    ctx = _load_order_email_context(order_id)
    if not ctx:
        return
    to = ctx.get("seller_email") if recipient == "seller" else ctx.get("customer_email")
    if not to:
        return
    lang = (ctx.get("seller_lang") if recipient == "seller" else ctx.get("customer_lang")) or "en"
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
```

**Extend `services/order_emails.py::dispatch_order_status_changed`:**

```python
def dispatch_order_status_changed(
    order_id: int,
    new_status: str,
    *,
    notify_seller: bool = False,
    reason: str | None = None,
) -> None:
    _safe_delay(send_order_status_changed_async, order_id, new_status, "customer", reason)
    if notify_seller:
        _safe_delay(send_order_status_changed_async, order_id, new_status, "seller", reason)
```

**Update callers:**

- `api/orders.py:292` (`transition_order` handler): no change needed (no reason for transitions).
- `api/orders.py:321` (`cancel` handler): change to `dispatch_order_status_changed(order.id, "cancelled", notify_seller=True, reason=reason)` — `reason` is the already-extracted local variable.

**Test (extend `test_order_emails.py`):** add a test that cancels an order with reason `"out of stock"` and asserts the captured `html` (seller path) contains `"Cancellation reason"` and `"out of stock"`. Assert the same for the customer path.

**Commit:** `feat(email): order_status_changed HTML with progress bar and cancel reason`.

### Task 14: `admin_order_action_seller`

**Create `admin_order_action_seller/subject.txt`:**

```
[{{ brand_name }}] Admin updated order #{{ order_id }}
```

**Create `admin_order_action_seller/preheader.txt`:**

```
{{ action_label }}{% if reason %} — {{ reason|truncate(60) }}{% endif %}
```

**Create `admin_order_action_seller/body.html`:**

```html
{% extends "base.html" %}
{% block body %}
  <p>Hi,</p>
  <p>An admin updated your order <strong>#{{ order_id }}</strong> ({{ service_name }}) at <strong>{{ store_name }}</strong>.</p>
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:16px 0;">
    <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;width:120px;">Action</td><td style="padding:6px 0;font-size:15px;font-weight:600;">{{ action_label }}</td></tr>
    <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">Reason</td><td style="padding:6px 0;font-size:15px;">{{ reason|default('(none provided)', true) }}</td></tr>
  </table>
  {% set cta_url = frontend_base_url ~ "/seller/orders/" ~ order_id|string %}
  {% set cta_label = "View order" %}
  {% include "_partials/button.html" %}
  <p style="color:#6b7280;font-size:14px;">If you have questions, reply to this email.</p>
{% endblock %}
```

**Create `admin_order_action_seller/body.txt`:**

```
Hi,

An admin updated your order #{{ order_id }} ({{ service_name }}) at {{ store_name }}.

Action : {{ action_label }}
Reason : {{ reason|default('(none provided)', true) }}

View order: {{ frontend_base_url }}/seller/orders/{{ order_id }}
```

**Add a small helper `_action_label(action)` in `worker.py`** (above `send_admin_order_action_seller_async`):

```python
_ACTION_LABELS = {
    "order.rewind": "Status reverted",
    "order.refund": "Refunded",
    "order.cancel": "Cancelled",
    "order.address_override": "Delivery address updated",
    "order.transition": "Status changed",
}


def _action_label(action: str) -> str:
    return _ACTION_LABELS.get(action, action)
```

**Rewrite the task (rename to `send_admin_order_action_seller_async`, keep Celery name for back-compat):**

```python
@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_admin_order_action_email",  # back-compat name; enqueues continue to use this
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_admin_order_action_seller_async(order_id: int, action: str, reason: str) -> None:
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
```

Also update the import in `services/order_emails.py` to use the new function name (the Celery `name=` argument keeps task identity intact).

**Test (extend `test_order_emails.py`):** assert `Refunded`, `duplicate payment`, and `/seller/orders/{id}` all appear in the rendered html.

**Commit:** `feat(email): admin_order_action_seller HTML template`.

### Task 15: `admin_order_action_customer` (NEW event)

**Create `admin_order_action_customer/subject.txt`:**

```
[{{ brand_name }}] Update on your order #{{ order_id }}
```

**Create `admin_order_action_customer/preheader.txt`:**

```
{{ action_label }} by our team.
```

**Create `admin_order_action_customer/body.html`:**

```html
{% extends "base.html" %}
{% block body %}
  <p>Hi {{ customer_first_name|default('there') }},</p>
  <p>Our team made a change to your order <strong>#{{ order_id }}</strong> ({{ service_name }}).</p>
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:16px 0;">
    <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;width:140px;">What changed</td><td style="padding:6px 0;font-size:15px;font-weight:600;">{{ action_label }}</td></tr>
    {% if reason %}
      <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">Reason</td><td style="padding:6px 0;font-size:15px;">{{ reason }}</td></tr>
    {% endif %}
    {% if action == 'order.address_override' %}
      <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">New address</td><td style="padding:6px 0;font-size:15px;">{{ delivery_address_snapshot }}</td></tr>
    {% endif %}
  </table>
  {% set cta_url = frontend_base_url ~ "/account/orders/" ~ order_id|string %}
  {% set cta_label = "View order" %}
  {% include "_partials/button.html" %}
  <p style="color:#6b7280;font-size:14px;">Questions? Reply to this email.</p>
{% endblock %}
```

**Create `admin_order_action_customer/body.txt`:**

```
Hi {{ customer_first_name|default('there') }},

Our team made a change to your order #{{ order_id }} ({{ service_name }}).

What changed : {{ action_label }}
{% if reason -%}
Reason       : {{ reason }}
{% endif -%}
{% if action == 'order.address_override' -%}
New address  : {{ delivery_address_snapshot }}
{% endif %}

View order: {{ frontend_base_url }}/account/orders/{{ order_id }}
```

**New worker task in `worker.py`:**

```python
@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_admin_order_action_customer_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_admin_order_action_customer_async(
    order_id: int, action: str, reason: str
) -> None:
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
```

**Extend the dispatcher in `services/order_emails.py`:**

```python
_CUSTOMER_NOTIFY_ACTIONS = frozenset(
    {"order.rewind", "order.refund", "order.cancel", "order.address_override"}
)


def dispatch_admin_order_action(order_id: int, action: str, reason: str) -> None:
    """Notify the seller (always) and the customer for impactful actions."""
    from app.worker import (
        send_admin_order_action_customer_async,
        send_admin_order_action_seller_async,
    )

    _safe_delay(send_admin_order_action_seller_async, order_id, action, reason)
    if action in _CUSTOMER_NOTIFY_ACTIONS:
        _safe_delay(send_admin_order_action_customer_async, order_id, action, reason)
```

(Remove the old import of `send_admin_order_action_email` from the top of the file; the renamed function `send_admin_order_action_seller_async` is imported here instead.)

**Test (`tests/test_admin_customer_email.py`):**

```python
import pytest


@pytest.mark.parametrize(
    "action,should_notify_customer",
    [
        ("order.rewind", True),
        ("order.refund", True),
        ("order.cancel", True),
        ("order.address_override", True),
        ("order.transition", False),
    ],
)
def test_dispatch_routes_customer_notification(monkeypatch, action, should_notify_customer):
    seller_calls = []
    customer_calls = []

    from app.worker import (
        send_admin_order_action_customer_async,
        send_admin_order_action_seller_async,
    )

    monkeypatch.setattr(
        send_admin_order_action_seller_async,
        "delay",
        lambda *a, **k: seller_calls.append(a),
    )
    monkeypatch.setattr(
        send_admin_order_action_customer_async,
        "delay",
        lambda *a, **k: customer_calls.append(a),
    )

    from app.services.order_emails import dispatch_admin_order_action

    dispatch_admin_order_action(123, action, "reason text")

    assert len(seller_calls) == 1
    assert (len(customer_calls) == 1) == should_notify_customer
```

**Commit:** `feat(email): admin_order_action_customer notification on refund/cancel/rewind/address-override`.

### Task 16: `order_review_request` (NEW event, 24h countdown)

**Create `order_review_request/subject.txt`:**

```
[{{ brand_name }}] How was order #{{ order_id }}?
```

**Create `order_review_request/preheader.txt`:**

```
Rate your {{ service_name }} order from {{ store_name }}.
```

**Create `order_review_request/body.html`:**

```html
{% extends "base.html" %}
{% block body %}
  <p>Hi {{ customer_first_name|default('there') }},</p>
  <p>Your <strong>{{ service_name }}</strong> order #{{ order_id }} from <strong>{{ store_name }}</strong> was delivered yesterday. How did it go?</p>
  <p style="margin:16px 0;">A rating and a short comment helps other shoppers find the right products and helps the seller improve.</p>
  {% set cta_url = frontend_base_url ~ "/account/orders/" ~ order_id|string %}
  {% set cta_label = "Rate your order" %}
  {% include "_partials/button.html" %}
  <p style="color:#6b7280;font-size:14px;">Takes less than a minute.</p>
{% endblock %}
```

**Create `order_review_request/body.txt`:**

```
Hi {{ customer_first_name|default('there') }},

Your {{ service_name }} order #{{ order_id }} from {{ store_name }} was delivered yesterday.

Leave a quick rating + comment:
{{ frontend_base_url }}/account/orders/{{ order_id }}

Takes less than a minute.
```

**New worker task:**

```python
@celery_app.task(  # type: ignore[untyped-decorator]
    name="send_order_review_request_async",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_order_review_request_async(order_id: int) -> None:
    from app.core.config import settings
    from app.core.email_render import render_email

    ctx = _load_order_email_context(order_id)
    if not ctx or not ctx.get("customer_email"):
        return
    payload = render_email(
        "order_review_request",
        {
            "order_id": ctx["order_id"],
            "service_name": ctx["service_name"],
            "store_name": ctx.get("store_name") or "a store",
            "customer_first_name": ctx.get("customer_first_name"),
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
```

**Trigger inside `services/order_emails.py::dispatch_order_status_changed`:**

```python
def dispatch_order_status_changed(
    order_id: int,
    new_status: str,
    *,
    notify_seller: bool = False,
    reason: str | None = None,
) -> None:
    from app.worker import (
        send_order_review_request_async,
        send_order_status_changed_async,
    )

    _safe_delay(send_order_status_changed_async, order_id, new_status, "customer", reason)
    if notify_seller:
        _safe_delay(send_order_status_changed_async, order_id, new_status, "seller", reason)
    if new_status == "delivered":
        try:
            send_order_review_request_async.apply_async(args=[order_id], countdown=86400)
        except _BROKER_ERRORS:
            logger.exception(
                "Failed to schedule order_review_request for order_id=%s", order_id
            )
```

**Test (`tests/test_order_review_email.py`):**

```python
def test_delivered_status_schedules_review_request(monkeypatch):
    captured = {}

    from app.worker import send_order_review_request_async

    def fake_apply_async(*args, **kwargs):
        captured["args"] = kwargs.get("args") or args
        captured["countdown"] = kwargs.get("countdown")

    monkeypatch.setattr(
        send_order_review_request_async, "apply_async", fake_apply_async
    )
    # Patch out the status-changed task so we focus on the review scheduling.
    monkeypatch.setattr(
        "app.worker.send_order_status_changed_async.delay", lambda *a, **k: None
    )

    from app.services.order_emails import dispatch_order_status_changed

    dispatch_order_status_changed(42, "delivered", notify_seller=False)

    assert captured["countdown"] == 86400
    assert captured["args"] == [42] or captured["args"] == (42,)


def test_non_delivered_status_does_not_schedule_review(monkeypatch):
    seen = []
    from app.worker import send_order_review_request_async

    monkeypatch.setattr(
        send_order_review_request_async,
        "apply_async",
        lambda *a, **k: seen.append(1),
    )
    monkeypatch.setattr(
        "app.worker.send_order_status_changed_async.delay", lambda *a, **k: None
    )

    from app.services.order_emails import dispatch_order_status_changed

    dispatch_order_status_changed(42, "packed")
    assert seen == []
```

**Side check (do this before writing the test):**

```bash
grep -rn "OrderReview\|review" frontend/src/app/account/orders/
```

If the order-detail page does not expose the review form for the recipient, add it as a small follow-up commit on this branch (`feat(orders): inline review form on order detail`). Use the existing `POST /api/v1/orders/{id}/review` endpoint (already implemented at `api/orders.py:329`). If the form is already present, note that in the commit message and skip.

**Commit:** `feat(email): order_review_request 24h after delivered`.

### Task 17: `customer_welcome` (NEW event)

**Create `customer_welcome/subject.txt`:**

```
[{{ brand_name }}] Welcome, {{ first_name }}
```

**Create `customer_welcome/preheader.txt`:**

```
You're all set. Start shopping from local stores near you.
```

**Create `customer_welcome/body.html`:**

```html
{% extends "base.html" %}
{% block body %}
  <p>Hi {{ first_name }},</p>
  <p>Welcome to <strong>{{ brand_name }}</strong>! You can now shop from local grocery, food, and pharmacy stores near you, with delivery in hours.</p>
  <ul style="padding-left:20px;line-height:1.7;">
    <li>Browse stores by service — grocery, food, pharmacy, and more.</li>
    <li>Compare prices across nearby stores for the same product.</li>
    <li>Pay via UPI at checkout; track every order from packing to delivery.</li>
  </ul>
  {% set cta_url = frontend_base_url ~ "/" %}
  {% set cta_label = "Start shopping" %}
  {% include "_partials/button.html" %}
  <p style="color:#6b7280;font-size:14px;">If you need help, reply to this email anytime.</p>
{% endblock %}
```

**Create `customer_welcome/body.txt`:**

```
Hi {{ first_name }},

Welcome to {{ brand_name }}! You can now shop from local grocery, food, and pharmacy stores near you, with delivery in hours.

• Browse stores by service.
• Compare prices across nearby stores.
• Pay via UPI; track every order.

Start shopping: {{ frontend_base_url }}/
```

**New helper + worker task in `worker.py`:**

```python
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
                        select(CustomerProfile).where(CustomerProfile.user_id == user_id)
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
```

**New dispatcher in `services/seller_emails.py`:**

```python
def dispatch_customer_welcome(user_id: int) -> None:
    from app.worker import send_customer_welcome_async

    _safe_delay(send_customer_welcome_async, user_id)
```

**Trigger in `api/auth.py`:** inside the new-user branch of `otp_verify` (at the location of `auth.py:136-143`), immediately after `await session.refresh(user)`:

```python
        from app.services.seller_emails import dispatch_customer_welcome

        if user.id is not None:
            dispatch_customer_welcome(user.id)
```

**Test (`tests/test_customer_welcome_email.py`):**

```python
import pytest


@pytest.mark.asyncio
async def test_first_otp_verify_enqueues_welcome(monkeypatch, client, ...):
    enqueued = []

    from app.worker import send_customer_welcome_async

    monkeypatch.setattr(
        send_customer_welcome_async, "delay", lambda *a, **k: enqueued.append(a)
    )

    # 1. POST /auth/otp/request → grab the code from Redis via the test helper.
    # 2. POST /auth/otp/verify with body.full_name="Ravi Kumar" — creates the user.
    # ...
    assert len(enqueued) == 1


@pytest.mark.asyncio
async def test_returning_user_otp_verify_does_not_enqueue_welcome(monkeypatch, client, ...):
    enqueued = []
    from app.worker import send_customer_welcome_async

    monkeypatch.setattr(
        send_customer_welcome_async, "delay", lambda *a, **k: enqueued.append(a)
    )
    # Verify once (creates user) — first call drains the welcome enqueue, reset.
    # Verify a second time with the same email — should NOT re-enqueue.
    # ...
    assert enqueued == []
```

The `...` blocks borrow the existing OTP-flow scaffolding in `tests/test_auth.py`.

**Commit:** `feat(email): customer_welcome on first OTP-verify`.

### Task 18: `support_message` rewrite + reply_to

**Create `support_message/subject.txt`:**

```
[Support] {{ user_subject }}
```

**Create `support_message/preheader.txt`:**

```
From {{ customer_email }}.
```

**Create `support_message/body.html`:**

```html
{% extends "base.html" %}
{% block body %}
  <p style="color:#6b7280;font-size:14px;">From: <strong style="color:#1f2937;">{{ customer_email }}</strong></p>
  <p style="color:#6b7280;font-size:14px;">Subject: <strong style="color:#1f2937;">{{ user_subject }}</strong></p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0;">
  <div style="white-space:pre-wrap;font-size:15px;line-height:1.6;">{{ message }}</div>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0;">
  <p style="color:#6b7280;font-size:13px;">Reply directly to this email to reach the customer.</p>
{% endblock %}
```

**Create `support_message/body.txt`:**

```
From: {{ customer_email }}
Subject: {{ user_subject }}

{{ message }}

— Reply directly to this email to reach the customer.
```

**Rewrite `send_support_email` in `worker.py`:**

```python
@celery_app.task(name="send_support_email")  # type: ignore[untyped-decorator]
def send_support_email(customer_email: str, subject: str, message: str) -> None:
    """Forward a customer support message to the configured SUPPORT_EMAIL inbox."""
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
```

**Test (extend `tests/test_customer_support.py`):**

```python
def test_support_email_dispatches_with_customer_reply_to(monkeypatch):
    captured = {}

    def fake_resolve(to, subject, body, *, html=None, reply_to=None):
        captured.update(to=to, subject=subject, html=html, reply_to=reply_to)

    monkeypatch.setattr("app.worker._resolve_email", fake_resolve)

    from app.worker import send_support_email

    send_support_email("user@example.com", "Order issue", "Help me with order #42")

    assert captured["subject"].startswith("[Support] Order issue")
    assert captured["reply_to"] == "user@example.com"
    assert "Order #42" in captured["html"] or "order #42" in captured["html"]
```

**Commit:** `feat(email): support_message template with customer reply_to`.

---

## Task 19: Final validation pass

- [ ] **Step 1: Run linters and types**

```bash
uv run ruff check .
uv run mypy .
```

Expected: clean.

- [ ] **Step 2: Run the full test suite**

```bash
uv run pytest -q
```

Expected: every test green, no warnings about unawaited coroutines or deprecation in the new code.

- [ ] **Step 3: Manual dev smoke — every template renders cleanly**

```bash
uv run python - <<'PY'
from app.core.email_render import render_email

events = [
    ("otp_login", {"code": "123456", "ttl_minutes": 10}),
    ("seller_approved", {"business_name": "Sample Mart"}),
    ("seller_rejected", {"business_name": "Sample Mart", "reason": "Documents missing"}),
    ("seller_application_submitted", {"business_name": "Sample Mart", "applicant_email": "owner@example.com", "submitted_at": "2026-05-21 10:00"}),
    ("order_placed_customer", {"orders": [{"order_id": 1, "service_name": "Grocery", "store_name": "Demo", "items": [{"name": "Apple", "qty": 2, "unit_price": 50.0, "line_total": 100.0}], "order_total": 100.0, "cta_url": "/account/orders/1"}]}),
    ("order_placed_seller", {"order_id": 1, "service_name": "Grocery", "store_name": "Demo", "items": [{"name": "Apple", "qty": 2, "unit_price": 50.0, "line_total": 100.0}], "order_total": 100.0, "cta_url": "/seller/orders/1"}),
    ("order_status_changed", {"order_id": 1, "service_name": "Grocery", "store_name": "Demo", "current": "packed", "reason": None}),
    ("admin_order_action_seller", {"order_id": 1, "service_name": "Grocery", "store_name": "Demo", "action": "order.refund", "reason": "duplicate"}),
    ("admin_order_action_customer", {"order_id": 1, "service_name": "Grocery", "action": "order.refund", "reason": "duplicate", "delivery_address_snapshot": "X"}),
    ("order_review_request", {"order_id": 1}),
    ("customer_welcome", {"first_name": "Ravi"}),
    ("support_message", {"customer_email": "a@b.com", "user_subject": "test", "message": "hi"}),
]
for event, ctx in events:
    payload = render_email(event, ctx, lang="en")
    print(f"OK {event}: {payload.subject!r} ({len(payload.html)} bytes)")
PY
```

Expected: 12 lines, each starting with `OK`.

- [ ] **Step 4: Open the previews**

```bash
ls -lh /tmp/khanabazaar_email_*.html | head
xdg-open /tmp/khanabazaar_email_*.html
```

Visually scan the rendered HTML in a browser. Check brand colors, the CTA buttons, line items, and the progress bar render as expected.

- [ ] **Step 5: Open a PR**

```bash
gh pr create --title "feat(email): HTML transactional emails, new events, OTP fallback" --body "$(cat <<'EOF'
## Summary
- Replace plain-text transactional emails with Jinja2 HTML templates (text fallback retained).
- Add four new events: customer_welcome, seller_application_submitted, admin_order_action_customer, order_review_request.
- Fix 10 audited bugs (see spec §audit).
- OTP delivery: inline send first; fall back to rewritten Celery task on `httpx.HTTPError`.
- No DB migration.

Spec: `docs/superpowers/specs/2026-05-21-email-overhaul-design.md`

## Test plan
- [ ] `uv run pytest -q` clean
- [ ] `uv run ruff check . && uv run mypy .` clean
- [ ] Manual smoke renders 12 events without exceptions
- [ ] Visually inspect HTML previews in a browser for layout + brand
- [ ] Verify a real Resend send in a staging environment for one event (e.g. otp_login)
EOF
)"
```

---

## Out-of-band follow-ups (do not include in this PR)

- Carve `docs/superpowers/specs/` and `docs/superpowers/plans/` out of `.gitignore` so future specs and plans commit without `-f`.
- Add `hi`, `mr`, `gu`, `pa` template overrides under `email_templates/{event}.{lang}/`.
- Switch `order_review_request` scheduling from Celery `countdown` to a DB-backed scheduler so broker restarts don't drop tasks.
- Daily seller new-order digest (coalescing across separate `POST /orders` calls).
- App Insights / OpenTelemetry email delivery success/failure metrics.
- CLAUDE.md addendum documenting the email template package, Jinja2 dep, locale routing rule.
