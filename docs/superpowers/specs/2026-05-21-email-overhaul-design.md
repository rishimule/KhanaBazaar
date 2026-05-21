# Email Overhaul — Design

**Status:** Draft
**Author:** Khana Bazaar Developer
**Date:** 2026-05-21
**Branch:** docs/email-overhaul-spec

## Goal

Bring transactional email up to production quality:

1. Fix audited bugs in current dispatch code.
2. Replace plain-text emails with branded HTML (+ text fallback) using Jinja2 templates.
3. Add four high-value missing events (customer welcome, seller-application admin alert, customer-side admin-action notice, post-delivery review request).
4. Keep current Celery-task topology; do not rewire transport.

Out of scope is listed in §10.

## Audit of current state

### Existing dispatchers and triggers

| Trigger site | Recipient | Path | Template subject |
| --- | --- | --- | --- |
| `api/auth.py:103` (customer + seller login OTP) | requestor email | inline `await sender.send()` | "Your Khana Bazaar login code" |
| `api/sellers.py:162` approve | seller `User.email` | Celery `send_seller_approved_async` | "Your Khana Bazaar seller application is approved" |
| `api/sellers.py:164` reject | seller `User.email` | Celery `send_seller_rejected_async` | "Update on your Khana Bazaar seller application" |
| `api/orders.py:276` order placed | customer + seller | Celery `send_order_confirmed_customer_async` (customer summary) + `send_order_placed_seller_async` (per-store) | "Your Khana Bazaar order is confirmed" / "New {service} order received at {store}" |
| `api/orders.py:292` status transition | customer | Celery `send_order_status_changed_async` | "Order #X · {service} status: {s}" |
| `api/orders.py:321` cancel | customer + seller | same Celery task, `notify_seller=True` | same |
| `api/orders.py:294`, `api/admin_actions.py:{309,332,356}` admin action | seller | Celery `send_admin_order_action_email` | "Admin updated your order #X" |
| `api/customers.py:243` support form | `SUPPORT_EMAIL` inbox | Celery `send_support_email` | "[Support] {subject}" |

### Bugs and gaps found

1. **`send_otp_email_async` Celery task is dead.** Defined in `worker.py:18` but no caller. Login OTP send is inline → blocks request on Resend outage with no retry.
2. **No HTML.** `EmailSender.send(to, subject, text)` only takes plain text. Resend supports `html` and `reply_to`.
3. **`SUPPORT_EMAIL` default is `support@khanabazaar.example`** — non-routable. Silent drop if env not overridden in prod.
4. **No `reply_to`.** Customer replies to order mail bounce.
5. **OTP body hardcodes "Expires in 10 minutes"** while TTL is config-driven (`OTP_TTL_SECONDS`). Drift risk.
6. **Order body shows raw `Decimal`** ("Order total: 234.50") with no currency symbol or grouping.
7. **No order line items** in customer confirmation. Industry standard for receipts.
8. **Cancel reason lost** — `send_order_status_changed_async` does not accept a reason, even when admin cancels with one.
9. **Customer not informed on admin actions.** `send_admin_order_action_email` only emails the seller; customer sees a generic status change with no "why."
10. **Inline OTP cannot retry.** A transient Resend 5xx fails the user's login request.

### Missing events worth adding (v1 scope)

- `customer_welcome` — on first OTP-verify that creates a `User` row.
- `seller_application_submitted` — alert `SUPPORT_EMAIL` so admin queue isn't invisible.
- `admin_order_action_customer` — when admin refunds, cancels, or overrides address.
- `order_review_request` — 24 h after `delivered`.

### Missing events deferred to v2

- Login-from-new-device security mail (no passwords in product; defer).
- Payment-received confirmation (payment status state machine is dormant).
- Seller daily new-order digest (coalescing requires Redis bucket + countdown; non-trivial, see §10).
- Unsubscribe / preferences page (transactional exempt).

## Design

### §1 Architecture

```
backend/app/src/app/
  core/
    email.py                  # extended EmailSender protocol + Console/Resend impls
    email_render.py           # NEW: Jinja2 Environment + render_email()
  utils/
    currency.py               # NEW: format_inr(Decimal) -> "₹1,234.50"
  email_templates/            # NEW package — loaded via PackageLoader("app", "email_templates")
    base.html
    _partials/
      button.html
      progress_bar.html
      line_items.html
      footer.html
    {event}/
      subject.txt             # supports {{ vars }}, single line
      preheader.txt           # ≤80 chars
      body.html
      body.txt                # plaintext fallback
    {event}.{lang}/           # optional per-locale override (en is the default base)
  services/
    order_emails.py           # dispatcher (existing, extended for new events)
    seller_emails.py          # existing
  worker.py                   # Celery tasks (existing + new tasks for the four new events)
```

`render_email(event: str, ctx: dict, lang: str = "en") -> EmailPayload` returns `{subject, preheader, html, text}`.
`EmailPayload` is a `dataclass` in `core/email_render.py`.

Templates load via `jinja2.PackageLoader("app", "email_templates")` so they ship with the wheel and resolve under Celery prefork without filesystem assumptions. Autoescape on for `.html`, off for `.txt`. `format_inr` registered as a Jinja filter.

#### Extended `EmailSender` protocol

```python
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
```

Keyword-only after `subject` keeps the breaking change explicit. `text` is required; `html` is optional. `ConsoleEmailSender` logs subject + text; in dev, when `html` is set, it also writes `/tmp/khanabazaar_email_{event}_{ts}.html` for visual inspection. `ResendEmailSender` posts `{from, to, subject, text, html?, reply_to?}` to the Resend API.

`ResendWithConsoleSender` keeps the existing dual-path semantics (log to console, then attempt Resend, swallow `HTTPStatusError`).

#### OTP delivery: inline send + Celery fallback

Replace `asyncio.wait_for` plan with HTTP-client timeout to avoid the success-vs-cancel race.

```python
# core/email.py — ResendEmailSender already uses httpx.AsyncClient; set timeout=3.0.
# api/auth.py:
try:
    await sender.send(to=email, subject=..., text=..., html=...)
except httpx.HTTPError:
    send_otp_email_async.delay(email, code)  # fallback path
```

If the inline call returns successfully, the email is sent and no fallback runs. If it raises (timeout, connection error, 5xx via `raise_for_status`), Celery picks it up with retry backoff. No double-send.

`send_otp_email_async` is rewritten to use `render_email("otp_login", ...)` so inline and fallback paths render the same template.

#### Settings additions (`core/config.py`)

| Key | Default | Purpose |
| --- | --- | --- |
| `EMAIL_REPLY_TO` | `SUPPORT_EMAIL` value | Reply-to header on customer-facing mails |
| `EMAIL_BRAND_NAME` | `"Khana Bazaar"` | Used in templates / subject prefix |
| `EMAIL_FRONTEND_BASE_URL` | `"http://localhost:3000"` | Base for CTA links (e.g. `/account/orders/{id}`) |
| Validator: warn loud if `ENVIRONMENT=production` and `SUPPORT_EMAIL` contains `.example` | — | Catch the placeholder drift |

No DB migration. No new tables or columns.

### §2 Template inventory

| Event slug | Recipients | Subject (en) | Primary CTA | Implementation |
| --- | --- | --- | --- | --- |
| `otp_login` | requestor | `[Khana Bazaar] Your login code` | n/a | New |
| `seller_otp_email` | seller signup | `[Khana Bazaar] Verify your email` | n/a | Rewrite of inline |
| `seller_approved` | seller `User.email` | `[Khana Bazaar] Your seller application is approved` | "Open seller dashboard" → `/seller` | Rewrite |
| `seller_rejected` | seller `User.email` | `[Khana Bazaar] Update on your seller application` | "Update application" → `/seller/signup` | Rewrite |
| `seller_application_submitted` | `SUPPORT_EMAIL` | `[Khana Bazaar] New seller application: {business_name}` | "Review applications" → `/admin/sellers` | **New** |
| `order_placed_customer` | customer | `[Khana Bazaar] Order #{order_id} confirmed` | "View order" → `/account/orders/{id}` | Rewrite + line items + progress bar |
| `order_placed_seller` | seller | `[Khana Bazaar] New {service} order #{order_id}` | "Open order" → `/seller/orders/{id}` | Rewrite + line items |
| `order_status_changed` | customer (always); seller on cancel | `[Khana Bazaar] Order #{order_id} is now {status}` | "View order" → `/account/orders/{id}` | Rewrite + progress bar + cancel reason |
| `admin_order_action_seller` | seller | `[Khana Bazaar] Admin updated order #{order_id}` | "View order" → `/seller/orders/{id}` | Rewrite |
| `admin_order_action_customer` | customer | `[Khana Bazaar] Update on your order #{order_id}` | "View order" → `/account/orders/{id}` | **New** — fires on refund/cancel/address_override |
| `order_review_request` | customer | `[Khana Bazaar] How was order #{order_id}?` | "Rate your order" → `/account/orders/{id}` (review form lives on order detail page) | **New** — Celery `apply_async(..., countdown=86400)`. Implementation plan must confirm the order-detail page exposes a review form for the recipient; if not, add it as part of the work. |
| `customer_welcome` | customer | `[Khana Bazaar] Welcome, {first_name}` | "Start shopping" → `/` | **New** — only on User creation |
| `support_message` | `SUPPORT_EMAIL` | `[Support] {subject}` | n/a (admin replies to customer) | Rewrite, `reply_to=customer.email` |

### §3 Bug fixes bundled into this overhaul

1. Delete dead `send_otp_email_async` body; replace with new template-rendering impl.
2. Remove hardcoded "10 minutes"; interpolate `settings.OTP_TTL_SECONDS // 60`.
3. `format_inr(value: float | Decimal) -> str` in `utils/currency.py`. Order monetary columns are SQLModel `float` (`models/commerce.py:69-72`), but the helper also accepts `Decimal` so future migration to `Numeric` doesn't break callers. Registered as Jinja filter `inr`. Renders `₹1,234.50` with comma grouping per Indian numbering convention. Implementation uses manual grouping (Python's `locale` module is process-global and unsafe to mutate in a server).
4. `dispatch_order_status_changed(order_id, new_status, *, notify_seller=False, reason=None)` — accepts reason, threaded to the Celery task and into template ctx.
5. Customer notification on admin action: `dispatch_admin_order_action` extended to enqueue `send_admin_order_action_customer_async` when `action in {"order.rewind", "order.refund", "order.cancel", "order.address_override"}`. `order.rewind` is included because `admin_actions.py::admin_rewind_order` does not fire `dispatch_order_status_changed` — without this the customer learns of the reverted state only by reopening the order page. `order.transition` is excluded because that path already calls `dispatch_order_status_changed(...)` separately. Both calls run inside `_safe_delay`.
6. Reply-to: customer-facing emails use `EMAIL_REPLY_TO`. Support inbox email uses the customer's email as reply-to so admin reply lands on the customer.
7. Subject prefix `[Khana Bazaar]` standard across every template.
8. Preheader injection in `base.html`:
   ```html
   <div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">
     {{ preheader }}&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;
   </div>
   ```
   Zero-width non-joiners + NBSPs pad past Gmail's "look-ahead into body" preview.
9. Startup validator: if `settings.ENVIRONMENT == "production"` and `SUPPORT_EMAIL` contains `.example`, log a loud `WARNING`. Implemented as a Pydantic `model_validator`.

### §4 Per-event context schemas

Loaders extended in `worker.py`:

- `_load_order_email_context(order_id)` extended to also fetch:
  - `items: list[{name, qty, unit_price, line_total}]` — straight `OrderItem` rows. `OrderItem` already stores `product_name_snapshot`, `unit_price_snapshot`, `quantity`, `line_total` at checkout time (`models/commerce.py:80-88`), so no `MasterProductTranslation` join is required. The item name reflects the catalog at order time, not the email recipient's current locale — that is correct for a receipt.
  - `customer_first_name`, `customer_lang`, `seller_lang` — for personalization + template routing. `customer_lang` and `seller_lang` come from `User.preferred_language` (`models/base.py:33`, non-null default `"en"`). `CustomerProfile.preferred_language` (`models/profile.py:31`) also exists but is `Optional[str]` and currently unused by any code path; this spec ignores it.
  - `delivery_address_after` — comes directly from `order.delivery_address_snapshot` after `override_delivery_address` mutates it (`services/orders.py:372`). No new formatter required.

- New helper `_load_seller_application_context(seller_profile_id)` for `seller_application_submitted`:
  - `business_name`, `applicant_email`, `submitted_at`.

- New helper `_load_customer_welcome_context(user_id)` for `customer_welcome`:
  - `first_name`, `lang`.

All loaders use the existing thread-bridged `asyncio.run` pattern (`worker.py:88-155`) for prefork + EAGER compatibility.

### §5 Locale routing

`User.preferred_language` (default `"en"`, defined `models/base.py:33`) drives template selection. Resolution:

- Customer email: `customer_user.preferred_language`.
- Seller email: `seller_user.preferred_language`.
- OTP request: no `User` row exists yet for new customers. Fall back to `"en"`. The HTTP handler may pass a hint from the `Accept-Language` header in a follow-up (out of v1 scope).
- Support inbox: always `"en"` (admin language).

Template lookup order: `{event}.{lang}/` → `{event}/` (English base). Missing locale silently falls back. For v1, ship only `en` templates; add `hi`, `mr`, `gu`, `pa` in a follow-up PR once `en` is reviewed.

### §6 New trigger wiring

- `customer_welcome`: in `api/auth.py:142` (after `await session.commit()` inside the `if user is None` branch), call `dispatch_customer_welcome(user.email, first_name)`. Gating on the new-user branch is mandatory — returning users must not get the welcome.
- `seller_application_submitted`: in `api/sellers.py` register-or-resubmit handler, after `session.commit()` and only when `verification_status == Pending`, call `dispatch_seller_application_submitted(profile.id)`.
- `order_review_request`: in `services/order_emails.py::dispatch_order_status_changed`, when `new_status == "delivered"`, enqueue `send_order_review_request_async.apply_async(args=[order_id], countdown=86400)`. Celery countdown is held in Redis; broker restart loses scheduled task. Acceptable for MVP — worst case the customer doesn't get the prompt. Document risk in §10.
- `admin_order_action_customer`: extend `dispatch_admin_order_action(order_id, action, reason)`. When `action in {"order.rewind", "order.refund", "order.cancel", "order.address_override"}`, additionally enqueue `send_admin_order_action_customer_async(order_id, action, reason)`.

### §7 Testing

- `tests/test_email_render.py` (new): for each event, build a fixture context, call `render_email`, assert subject/preheader/html contain the expected variables, render under `jinja2.StrictUndefined` so missing keys raise instead of silently producing empty strings, and assert no template syntax leaks (no `{{ ` left in output).
- `tests/test_order_emails.py` extended: assert the new dispatchers fire for the four new events. Patch the worker's `_resolve_email` and the `send_*` task `.delay` to capture args (same pattern as existing tests).
- No snapshot library introduced. Tests assert that rendered HTML contains structural anchors (CTA URL, item name, status string, brand name) — robust to cosmetic template edits. Pure byte-equal snapshots would add churn without catching real regressions.
- Console sender in dev optionally writes a copy to `/tmp/khanabazaar_email_{slug-of-subject}_{ts}.html` when `html` is non-empty, so the developer can open the file in a browser for visual review. The file path is logged at INFO level. Off in tests (no `/tmp` write).

### §8 Migration / breaking changes

- `EmailSender.send()` signature changes. Callers updated in the same PR:
  - `api/auth.py:103` — customer/seller email OTP.
  - The dead Celery task body in `worker.py:18` — rewrites to use `render_email` + `get_email_sender().send(...)`.
- All `_resolve_email` callers (worker.py order/seller tasks) updated to call `render_email` first, then `get_email_sender().send(...)` with both `html` and `text`.
- No DB migration.
- No frontend changes (email is server-side).

### §9 Rollout

Single PR. Behind no feature flag — every email path is upgraded together. Easy to revert via `git revert` if Resend HTML payload causes provider-side issues.

### §10 Out of scope (explicit)

- Login-from-new-device / password-reset security mails.
- Marketing or promotional emails.
- Unsubscribe preferences page.
- Seller daily new-order digest (coalescing across separate `POST /orders` calls requires Redis bucket + countdown; non-trivial). Tracked for v2.
- App Insights / OpenTelemetry email delivery metrics (deployment-tier, separate spec).
- Non-English templates (ship `en` only; add Indian languages in a follow-up).
- Switching review-request scheduling from Celery `countdown` to a DB-scheduled job. MVP accepts the broker-restart risk.
- MJML build pipeline.

### §11 Failure modes for Celery email tasks

`worker.py` order/seller tasks declare `autoretry_for=(Exception,)` with `max_retries=3` and `retry_backoff=True`. That intentionally retries on transient broker/Resend issues but also retries on template bugs (`jinja2.UndefinedError`, etc.). For MVP we accept that: template bugs surface in dev under `StrictUndefined` tests; in prod a template-bug task fails 3× then drops to Celery's failed-task log and surfaces in operator dashboards. We do not add a sentinel exception type or split the retry policy now; revisit if template errors become noisy post-launch.

## Risks and trade-offs

- **Resend HTML rejection.** Resend renders almost any HTML, but inline-CSS only. Templates avoid `<style>` blocks; all styling is `style=""` attributes on tables. Validate via `litmus`-style preview (manual, dev-only).
- **Snapshot churn.** Pixel-equal snapshots break on benign template edits. Snapshot tests target *structural* assertions (must-contain strings) rather than byte equality of the whole HTML where the body changes often. Re-evaluate after the first month.
- **Locale fallback for OTP.** New customers default to `en` because no `User` row exists. Acceptable; v2 reads `Accept-Language` header.
- **Celery countdown loses scheduled review-request tasks on broker restart.** Acceptable for MVP. Will switch to a DB-backed scheduler if customer-engagement matters.

## Files this spec touches when implemented

```
backend/app/src/app/core/email.py            (signature change + impls)
backend/app/src/app/core/email_render.py     (new)
backend/app/src/app/core/config.py           (3 new settings + validator)
backend/app/src/app/utils/currency.py        (new)
backend/app/src/app/email_templates/         (new package — base, partials, 13 event dirs)
backend/app/src/app/worker.py                (rewrite OTP/order/seller tasks + 4 new tasks + extended loader)
backend/app/src/app/services/order_emails.py (extend dispatcher signatures)
backend/app/src/app/services/seller_emails.py (extend dispatcher for application_submitted)
backend/app/src/app/api/auth.py              (welcome trigger + new OTP send path)
backend/app/src/app/api/sellers.py           (application_submitted trigger)
backend/app/src/app/api/orders.py            (no change — dispatcher signatures stay compatible at call sites)
backend/app/src/app/api/customers.py         (support email reply_to)
backend/app/pyproject.toml                   (add jinja2 dep)
backend/app/tests/test_email_render.py       (new)
backend/app/tests/test_order_emails.py       (extend)
backend/app/tests/fixtures/emails/           (snapshot fixtures)
docs/superpowers/specs/2026-05-21-email-overhaul-design.md (this file)
```

## Open follow-ups (post-merge)

- Add `hi`, `mr`, `gu`, `pa` template variants.
- CLAUDE.md addendum: document the email templates package + Jinja2 dep + locale routing rule.
- Seller daily new-order digest spec.
- Switch review-request scheduling to a DB-backed scheduler.
- App Insights wiring for email delivery success/failure metrics.
