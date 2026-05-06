# Seller Signup — Phone-Number OTP Verification

**Date:** 2026-05-05
**Scope:**
- Backend: `backend/app/src/app/core/{otp.py,sms.py,security.py,config.py}`, `backend/app/src/app/api/auth.py`, `backend/app/src/app/schemas/sellers.py`, `backend/app/src/app/worker.py`, new tests under `backend/app/tests/`.
- Frontend: `frontend/src/app/(operator)/seller/signup/page.tsx`, signup wizard step components.
- No DB schema change (`SellerProfile.phone` already exists, required + unique).

## Problem

Seller registration today verifies only the seller's **email** before the wizard creates a `User` + `SellerProfile`. The phone number on the seller profile is captured as plain text, never proven, and there is no defence against typos or impersonation. Production rollout requires a working SMS-OTP gate before account creation. Until then, dev environments need a sandbox SMS path mirroring the existing `EMAIL_PROVIDER=console` switch.

Goals:

1. Add a phone-OTP step to the seller signup wizard, right after the email-OTP step, before any data-entry steps.
2. Reuse the existing OTP primitives (Redis-backed, hashed code, attempts/cooldown/hourly limits) — no parallel implementation.
3. Introduce a generic SMS sender abstraction with `console` (sandbox, default) and `twilio` (production) implementations, mirroring `core/email.py`.
4. Replace the existing `email_token` hand-off into `/auth/seller/register` with a combined `signup_token` that proves *both* email and phone are verified, and carries the verified phone in its claims.
5. Reject registration of a phone number that is already in use *before* dispatching SMS, so we never spend an SMS on a request that cannot succeed.
6. Restrict accepted phone numbers to Indian E.164 format (`+91[6-9]\d{9}`) — the platform is India-only.

Non-goals:

- Voice-call OTP fallback.
- Per-locale phone formats (only `+91` for now).
- Editing or re-verifying phone after registration (separate, future work).
- Backwards-compat shims for the old `/auth/seller/register` body shape — pre-production, clean cutover.

## Wizard flow change

Current sequence (6 steps):

```
1. Email
2. Email-OTP                 → returns email_token
3. Personal info             (full_name, phone)
4. Business info             (business_name, service_ids, address)
5. Compliance & banking      (gst, fssai, bank)
6. Review                    → POST /auth/seller/register {email_token, phone, ...}
```

New sequence (8 steps; phone moves out of "personal info"):

```
1. Email
2. Email-OTP                 → returns email_token
3. Phone                     (E.164 input, locked +91 prefix)  → POST /auth/seller/phone/otp/request
4. Phone-OTP                 (6-digit code)                    → POST /auth/seller/phone/otp/verify → returns signup_token
5. Personal info             (full_name only)
6. Business info             (business_name, service_ids, address)
7. Compliance & banking      (gst, fssai, bank)
8. Review                    → POST /auth/seller/register {signup_token, full_name, business_name, service_ids, address, ...}
```

Why this ordering:

- Phone capture happens *before* the heavy data-entry steps. A bad number / undeliverable SMS is caught when the user has invested ~30 seconds, not 5 minutes.
- One verification per step matches the existing email-OTP UX cadence.
- `phone` no longer travels through the request body of `/auth/seller/register` — it lives in the signed `signup_token` claims and cannot be tampered with at the final step.

## Backend design

### `core/sms.py` (new)

Mirrors `core/email.py` exactly:

```python
class SMSSender(Protocol):
    async def send(self, to: str, text: str) -> None: ...

class ConsoleSMSSender:
    async def send(self, to: str, text: str) -> None:
        logger.info("[SMS] to=%s\n%s", to, text)
        print(f"[SMS] to={to}\n{text}")

class TwilioSMSSender:
    async def send(self, to: str, text: str) -> None:
        # POST https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json
        # form-encoded body: From=<settings.TWILIO_FROM_NUMBER>, To=<to>, Body=<text>
        # HTTP basic auth: (settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        # raise_for_status on non-2xx (matches Resend behaviour)

@lru_cache(maxsize=1)
def get_sms_sender() -> SMSSender:
    if settings.SMS_PROVIDER == "twilio":
        return TwilioSMSSender()
    return ConsoleSMSSender()
```

No SDK dependency — raw `httpx.AsyncClient` POST, same posture as Resend.

### `core/config.py` additions

```
SMS_PROVIDER: Literal["console", "twilio"] = "console"
TWILIO_ACCOUNT_SID: str | None = None
TWILIO_AUTH_TOKEN: str | None = None
TWILIO_FROM_NUMBER: str | None = None       # E.164, e.g. "+15005550006"
```

`TWILIO_*` vars validated only when `SMS_PROVIDER == "twilio"` (Pydantic `model_validator`, same pattern as Resend).

### `core/otp.py` refactor — namespace argument

Today every helper is hard-coded to the email key prefix (`otp:code:`, `otp:cooldown:`, `otp:hourly:`). Add a `namespace` parameter so the same primitives drive both channels.

Signature change:

```python
def _key_code(identifier: str, namespace: str = "email") -> str:
    return f"otp:{namespace}:code:{identifier}"
# (and _key_cooldown, _key_hourly identically)

async def request_otp(identifier: str, redis, *, namespace: str = "email") -> str: ...
async def verify_otp(identifier: str, code: str, redis, *, namespace: str = "email") -> bool: ...
async def consume_otp_key(identifier: str, redis, *, namespace: str = "email") -> None: ...
```

Default `namespace="email"` keeps existing email call sites working without edits **and** preserves the current `otp:code:{email}` Redis key shape — no migration of in-flight email OTPs.

Phone call sites pass `namespace="phone"`. The `normalize_email` helper stays where it is; a new `normalize_phone(raw: str) -> str` lives in `core/otp.py` (strips spaces/hyphens, enforces `+91[6-9]\d{9}`, returns canonical E.164). Invalid input raises `InvalidPhoneNumber` → 400.

Reused, unchanged: `OTP_TTL_SECONDS`, `OTP_MAX_ATTEMPTS`, `OTP_RESEND_COOLDOWN`, `OTP_MAX_PER_HOUR`, `OTP_PEPPER`, `generate_code`, `hash_code`, exception types.

### `core/security.py` — combined signup token

Replace `create_email_verification_token` / `decode_email_verification_token` with a slightly broader pair:

```python
def create_seller_email_token(email: str) -> str:
    # type=seller_email, sub=email, exp=now+10min  (renamed from seller_otp; behaviour identical)

def create_seller_signup_token(email: str, phone: str) -> str:
    # type=seller_signup, sub=email, phone=<E.164>, exp=now+10min

def decode_seller_email_token(token: str) -> str:
    # returns email; rejects type != seller_email

def decode_seller_signup_token(token: str) -> tuple[str, str]:
    # returns (email, phone); rejects type != seller_signup
```

Both use `JWT_SECRET` HS256, 10-min TTL — same as today. Type strings differ so a stale `email_token` cannot be replayed at `/auth/seller/register`.

Backward-compat: rename `seller_otp` → `seller_email` in token claims. Pre-production cutover; no live tokens to honor.

### New / changed endpoints

All under `/api/v1/auth`.

| Endpoint                          | Auth gate     | Body                                  | Returns                            |
|-----------------------------------|---------------|---------------------------------------|------------------------------------|
| `POST /seller/otp/verify`         | (unchanged)   | `{email, code}`                       | `{email_token}` (claim type=`seller_email`) |
| `POST /seller/phone/otp/request`  | `email_token` | `{email_token, phone}`                | `{ok, expires_in}`                 |
| `POST /seller/phone/otp/verify`   | `email_token` | `{email_token, phone, code}`          | `{signup_token}` (claim type=`seller_signup`) |
| `POST /seller/register`           | `signup_token`| `SellerRegisterBody` (no `phone` field, `email_token` → `signup_token`) | `{access_token, token_type, user}` |

Notes:

- `/seller/phone/otp/request` validates `email_token`, normalizes `phone`, checks `SellerProfile.phone` uniqueness in DB **and** that no `User` with that email already exists (parallel to today's email check), then calls `request_otp(phone, redis, namespace="phone")` and dispatches the SMS via `send_otp_sms_async.delay(to=phone, code=code)`.
- `/seller/phone/otp/verify` validates `email_token`, normalizes `phone`, runs `verify_otp(phone, code, redis, namespace="phone")`, then on success calls `consume_otp_key(phone, redis, namespace="phone")` and mints `signup_token(email_from_token, phone)`. The email and phone are first cryptographically linked when the `signup_token` is signed — there is no pre-verify Redis record tying them together. This is safe because the OTP code is delivered to the phone number, so an attacker minting a `signup_token` for `(email_A, phone_X)` still requires receiving the SMS at `phone_X`.
- `/seller/register` takes the `signup_token`, decodes `(email, phone)` from claims, drops `phone` from the request body entirely. Re-checks duplicate email and duplicate phone at commit time (defence in depth — the uniqueness check at OTP-request time can race a concurrent registration).

Failure mapping (consistent with existing OTP endpoints):

| Condition                                   | Status | `error` code               |
|---------------------------------------------|--------|----------------------------|
| Phone fails E.164 / `+91` regex             | 400    | `invalid_phone`            |
| Phone already registered (pre-OTP check)    | 409    | `phone_already_registered` |
| Email_token expired / wrong type / invalid  | 410/400| (existing email-token errors) |
| Phone-OTP cooldown active                   | 429    | `rate_limited`             |
| Phone-OTP hourly cap                        | 429    | `rate_limited`             |
| Wrong code                                  | 400    | `invalid_code`             |
| Too many wrong codes                        | 429    | `too_many_attempts`        |
| Code expired or never issued                | 410    | `code_expired_or_used`     |
| Signup_token expired / wrong type / invalid | 410/400| `signup_token_expired` / `invalid_signup_token` |

### `worker.py` — Celery task

```python
@celery_app.task(name="send_otp_sms_async")
def send_otp_sms_async(to: str, code: str) -> None:
    # mirrors send_otp_email_async — sync wrapper that runs the async sender
    # body text: "Your Khana Bazaar seller verification code is: {code}\nExpires in 10 minutes."
```

Same eager-mode treatment in tests; same patch-to-no-op pattern in test fixtures.

### `schemas/sellers.py` change

`SellerRegisterBody`:

- Remove field `email_token: str` → add `signup_token: str`.
- Remove field `phone: str` (now sourced from token claims).
- All other fields unchanged.

New schemas (alongside existing `SellerOtpVerifyBody`):

```python
class SellerPhoneOtpRequestBody(BaseModel):
    email_token: str
    phone: str  # validated as E.164 +91 in the route handler via normalize_phone

class SellerPhoneOtpVerifyBody(BaseModel):
    email_token: str
    phone: str
    code: str
```

## Frontend design

### `frontend/src/app/(operator)/seller/signup/page.tsx`

Wizard state additions:

- `phone: string` — already exists; remains in state but is now collected on **step 3** instead of step 3 (personal info).
- `phoneCode: string` — new; OTP code entered on step 4.
- `signupToken: string | null` — new; replaces the role of `emailToken` past step 4. `emailToken` is still set after step 2 and is needed to call the phone-OTP endpoints.

State transitions:

| Step | UI                                                                | API on "Next"                                            |
|------|-------------------------------------------------------------------|----------------------------------------------------------|
| 1    | Email input + "Send code"                                         | `POST /auth/otp/request {email}`                         |
| 2    | OTP input + "Resend"                                              | `POST /auth/seller/otp/verify {email, code}` → `emailToken` |
| 3    | Phone input (locked `+91` prefix, 10-digit field) + "Send code"   | `POST /auth/seller/phone/otp/request {email_token, phone}` |
| 4    | Phone OTP input + "Resend"                                        | `POST /auth/seller/phone/otp/verify {email_token, phone, code}` → `signupToken` |
| 5    | `full_name` input                                                 | (local validation only)                                  |
| 6    | business_name + service_ids + address                             | (local validation only)                                  |
| 7    | gst + fssai + bank fields (all optional)                          | (local validation only)                                  |
| 8    | Review summary + Submit                                           | `POST /auth/seller/register {signup_token, full_name, ...}` (no `phone`, no `email_token`) |

UI rules:

- Phone input: `<input type="tel" inputMode="numeric" maxLength={10} pattern="[6-9][0-9]{9}">` rendered with a fixed `+91` adornment to the left, similar to the existing OTP pin styling. The wizard sends the assembled `+91XXXXXXXXXX` value to the backend.
- Resend rules and cooldown timer mirror the existing email-OTP step: read `expires_in` from the response, display countdown, disable resend during cooldown.
- Error mapping: `phone_already_registered` shows "This phone number is already registered" inline above the input on step 3; `invalid_phone` shows "Enter a valid 10-digit Indian mobile number".
- Going Back from step 4 → step 3 clears `phoneCode` only; the existing `phone` value is preserved so the user can edit it. If the user edits `phone` on step 3, hitting "Send code" issues a fresh OTP keyed to the new normalized phone; the previous Redis key expires naturally. The wizard does not allow advancing to step 4 without first calling `/seller/phone/otp/request` for the *current* `phone` value, so a phone-edited-between-request-and-verify flow cannot occur.
- Going Back from step 5 → step 4 keeps the `signupToken`. We do not invalidate it on every back navigation — it expires naturally in 10 min. If it expires before submit, step 8 surfaces the `signup_token_expired` error and offers a "Verify phone again" CTA that jumps the user back to step 3.

### `frontend/src/lib/api.ts`

Add three thin wrappers (`requestSellerPhoneOtp`, `verifySellerPhoneOtp`, updated `registerSeller` signature). No structural changes to `ApiError`.

## Rate-limit interaction

Phone OTP uses the same Redis-backed counters as email OTP, namespaced per channel. Numerically:

- Email: ≤5 sends/hour per email, 60s resend cooldown, 5 wrong attempts before lockout.
- Phone: ≤5 sends/hour per phone, 60s resend cooldown, 5 wrong attempts before lockout.

A single signup attempt by a determined user therefore consumes at most 5 SMS in a rolling hour. A flood from a single attacker against a victim phone can burn 5 SMS/hour — acceptable for MVP; the IP-level rate limit on `/seller/phone/otp/request` (handled by the existing `rate_limit.py` middleware-style helpers) caps cross-victim abuse from one source.

We do **not** add a separate IP-scoped counter in this spec; reuse the per-identifier hourly cap. If abuse becomes a concern post-launch, extend `request_otp` with an additional IP-scoped counter — out of scope here.

## Testing

`backend/app/tests/test_seller_phone_otp.py` (new):

- Patch `send_otp_sms_async.delay` to no-op (mirrors email tests in `conftest.py`).
- Helpers: `mint_email_token(email)`, `mint_signup_token(email, phone)` — call the security helpers directly so tests don't need the Redis OTP round-trip.
- Cases:
  - `test_phone_request_happy_path` — valid email_token + new phone → 200, Redis key created.
  - `test_phone_request_rejects_invalid_format` — malformed phone → 400 `invalid_phone`.
  - `test_phone_request_rejects_duplicate` — existing `SellerProfile.phone` → 409 `phone_already_registered`.
  - `test_phone_request_rejects_bad_email_token` — expired/wrong-type token → 410/400 (matches existing email-token errors).
  - `test_phone_verify_happy_path` — correct code → returns `signup_token`, type claim = `seller_signup`, `phone` claim matches.
  - `test_phone_verify_wrong_code` — 400 `invalid_code`, attempts counter increments.
  - `test_phone_verify_too_many_attempts` — 5 wrong codes → 429 `too_many_attempts`, key purged.
  - `test_phone_verify_expired` — code TTL elapsed → 410.
  - `test_resend_cooldown` — second request inside 60s → 429 `rate_limited` with `retry_after` body.
  - `test_hourly_cap` — 6th request inside the hour → 429.

`backend/app/tests/test_seller_register.py` updates:

- All happy-path and validation tests switched to mint `signup_token` (not `email_token`).
- New `test_register_rejects_email_token_used_as_signup_token` — replay protection via `type` claim.
- New `test_register_duplicate_phone` — second register with same phone (race window after OTP verify) → 409.
- Existing duplicate-email test continues to pass.

`tests/conftest.py`:

- Auto-patch `app.worker.send_otp_sms_async.delay` to a no-op (parallel to the existing email patch).

No frontend tests (CLAUDE.md: "No frontend tests configured.").

## Migration & rollout

- No Alembic migration: `SellerProfile.phone` column already exists with the right shape (str, max_length=20, NOT NULL, unique).
- Default `SMS_PROVIDER=console` keeps dev/sandbox + CI working without Twilio creds.
- Production deployment sets `SMS_PROVIDER=twilio`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` (Azure Key Vault secrets — `docs/azure_deployment.md` listing must be updated as part of implementation).
- The wizard cutover ships in one PR; no feature flag — pre-production app.

## Open risks / acknowledged trade-offs

- **One-token vs two-token bridge.** A combined `signup_token` is used instead of carrying two tokens (`email_token` + a separate `phone_token`) to `/seller/register`. Rationale: the register endpoint validates *one* signature, and the `phone` claim is bound to the email by the same signature, so no consistency check is needed at register time. The trade-off: a single `signup_token` leak is a complete signup bypass for that (email, phone) pair until expiry. Mitigated by the 10-min TTL and HTTPS-only transport.
- **Phone uniqueness pre-check is racy.** Two parallel requests for the same phone can both pass the pre-OTP duplicate check and dispatch SMS. The committing transaction in `/seller/register` re-checks (DB unique index also enforces). Cost: at most one wasted SMS in the racing case. Acceptable.
- **Indian-only format.** `+91` lock means non-resident owners cannot register. Acceptable for current market scope; revisit if international sellers become a use case.
- **No SMS-failure feedback path.** If Twilio rejects the SMS (invalid number not caught by regex, carrier block), the user sees a generic OTP-not-received UX (resend cooldown, eventual timeout). Production observability will need a Celery error metric on `send_otp_sms_async` failures — flagged for the deployment story, out of scope here.
