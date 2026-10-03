# Courier delivery (long-distance orders)

Courier delivery lets a store ship to customers **beyond its local delivery radius**, up to a courier radius it sets. The seller only knows the real courier charge once they see the parcel and the destination, so the flow is quote-first:

> customer places the order (no delivery charge yet) → seller quotes the courier charge and the delivery time → customer accepts → customer pays the seller directly (UPI or bank transfer) → seller confirms the money → seller packs and ships, with optional tracking → delivered.

There is **no delivery OTP**, payment is **prepaid only**, tracking is **optional**, and courier orders **cannot be returned** in the app.

This page is the reference for the whole feature: backend rules, API, error codes, frontend screens, configuration and deploy notes. The step-by-step request flow also lives in [`flows.md` §13](flows.md#13-courier-orders-long-distance-delivery), and the condensed gotchas live in `CLAUDE.md` under *Courier orders*. The design spec and the two implementation plans are worktree-local working documents (`docs/superpowers/` is gitignored), so this page is meant to stand on its own.

---

## 1. Who can use it

An address can take a courier order from a store only when **all** of these hold:

| Rule | Where it lives |
|---|---|
| The address is beyond `Store.delivery_radius_km` but within `Store.courier_radius_km` (the courier ring). | `services/serviceability.py` (`zone_for_point`, PostGIS `ST_DWithin`) |
| The service has `SellerProfileService.courier_enabled = true`. | same |
| The seller has a **live prepaid payee**: UPI (`upi_enabled` + `upi_vpa`), or bank transfer (`bank_transfer_enabled` + account name + account number + IFSC). | `serviceability.courier_payment_methods` |
| The point is inside the India bounding box. At checkout the saved address must also have `country == "India"` and a 6-digit PIN, because the bbox also covers Nepal and Bangladesh. | `serviceability.is_courier_destination`, `checkout.py` |
| The store and service are not paused, and the seller is approved. | Enforced at checkout and in listings exactly as for local orders. Zones carry no availability rules. |

`POST /api/v1/geo/serviceability` with a `store_id` returns:

- `serviceable`, which keeps its **local-only** meaning so older callers are unaffected;
- `zone`: `local` | `courier` | `none`;
- `courier_service_ids`: the services that can ship there. Without `service_id`, `zone: "courier"` means *some* service ships. With `service_id`, it means *that* service does.

---

## 2. Lifecycle

```
pending ──quote──▶ quoted ──accept──▶ accepted ──confirm payment──▶ paid ──▶ packed ──▶ dispatched ──▶ delivered
   │      (revise: stays quoted)         │  ▲                                    │            │
   │                                     │  └── "not received" (claim cleared)   │            │
   └──────────────── cancelled ◀─────────┴───────────────────────────────────────┴────────────┘
```

- Courier orders use their own transition table, `services/courier_rules.COURIER_TRANSITIONS`. Door delivery and pickup keep `LEGAL_TRANSITIONS`, and `transition_order_status` picks the table per mode.
- `OrderStatus.Paid` was defined but never used before. For courier it now means "the seller confirmed the money arrived".
- `OrderStatus.Quoted` and `OrderStatus.Accepted` are new. Both count as **active** (`ACTIVE_ORDER_STATUSES`), so they show in "active" lists and block account deactivation like any open order.
- Every courier action, plus `transition` and `cancel`, takes a `SELECT … FOR UPDATE` on the order (`courier_rules.lock_order`), so concurrent taps serialise.

| Step | Who | Endpoint | Result |
|---|---|---|---|
| Place | Customer | `POST /orders` with `delivery_mode: "courier"`, `recipient_name`, `recipient_phone` | `pending`, `delivery_fee = 0`, stock reserved, store credit covers the goods |
| Quote / revise | Seller (own store) | `POST /orders/{id}/courier/quote` | `quoted`; append-only versions |
| Accept | Customer (owner) | `POST /orders/{id}/courier/accept` `{quote_id}` | `accepted`, or `paid` when ₹0 is payable |
| "I've paid" | Customer (owner) | `POST /orders/{id}/payment/claim` `{method}` | stamps `payment.customer_claimed_at`; status unchanged |
| Payment received | Seller | `POST /orders/{id}/payment/confirm` | `paid`; fixes `eta_from` / `eta_to` |
| Not received | Seller | `POST /orders/{id}/payment/not-received` `{note?}` | clears the claim and records the note; still `accepted` |
| Pack | Seller / admin | `POST /orders/{id}/transition` `{to: "packed"}` | `packed` |
| Ship | Seller / admin | `POST /orders/{id}/transition` `{to: "dispatched", carrier_name?, tracking_number?, tracking_url?}` | `dispatched`; **no OTP issued** |
| Edit tracking | Seller (own store), while `dispatched` | `PATCH /orders/{id}/courier/tracking` | omitted = unchanged, `""` = clear |
| Deliver | Seller (`transition` → `delivered`), customer (`POST /orders/{id}/courier/received`), or admin (`transition` with `reason`) | | `delivered`; `order_courier.delivered_by` records who |
| Refund sent | Seller | `POST /orders/{id}/payment/refund-sent` `{reference?}` | stamps `payment.refunded_at`, sets `refunded` |

---

## 3. Money

- **Quotes are append-only** (`courier_quote`). The limit is `COURIER_MAX_QUOTE_VERSIONS` versions (default 5), after which you get `409 too_many_quote_versions`. Customers see only the latest version; sellers and admins see them all.
- **Accept names the version the customer saw** (`quote_id`). If the seller revised the quote in the meantime → `409 quote_superseded`, and the page shows the new quote. Accepting the same version twice is a no-op.
- On accept:
  - the charge is copied into `Order.delivery_fee`, and `Order.total` is recalculated;
  - store credit **tops up** as a second ledger entry, so credit the customer still holds at that store also goes toward the courier charge;
  - `Payment.amount` becomes `total − store_credit_applied`, the net amount payable.
  - Cancelling later reverts both credit entries (`revert_order(store_credit_applied)`).
- **₹0 payable** (store credit covered everything) skips straight to `paid`, and the customer is told.
- **Order-value fees:** the courier charge is **excluded** from the platform's order-value % fee. Courier rows use `total − delivery_fee` (`fee_order_value.compute_order_value_sales`).
- **Refunds:** cancelling after the money arrived leaves `Payment.status = paid`. On a cancelled order, `Paid` **is** the "refund due" state (`OrderRead.courier.refund_due`). It ends when either:
  - the seller records `payment/refund-sent`, with an optional UTR reference; or
  - an admin uses the refund marker (`POST /admin/orders/{id}/refund`).

  Both stamp `refunded_at` and `refunded_by_user_id`. The usual "Paid → Refunded on cancel" flip is skipped for courier.
- Before acceptance the courier charge is **not** in `Order.total`. Every list and total therefore renders `₹X + courier` while the order is `pending` or `quoted` (frontend `courierChargePending`).

---

## 4. Payment

- **Prepaid only.** The method is `upi` or `net_banking` (labelled "Bank transfer"). Cash, pay-at-store and postpaid credit are all refused. At checkout the method is a *preference*; the customer can pay by any live method once they accept.
- Bank details (`OrderRead.courier.bank_transfer`) are exposed **only to the owning customer, only while the order is `accepted`**.
- `payable_methods` lists the methods that are live right now. If every payee disappears after acceptance:
  - accept and claim answer `409 courier_payment_unavailable`;
  - the seller is told once (`payee_missing`);
  - the customer's pay panel says the store can't take payments yet.
- **Claim:** the customer must send `{method}` (`422 payment_method_required` otherwise). The seller is notified once per claim.
- **Confirm** works before a claim too, for a seller who sees the money arrive first. It fixes `eta_from` and `eta_to` as IST today plus the quoted days.
- **Not received** needs a claim (`409 no_claim`). It clears the claim and shows the seller's note to the customer, who can check and pay again. Each rejection bumps `payment_claim_rejection_count`, which starts a new reminder stage.

---

## 5. Cancelling

| Who | Allowed | Notes |
|---|---|---|
| Customer | `pending`, `quoted` (declining the quote), and `accepted` **until they tap "I've paid"** | After a claim → `403 cancel_not_allowed`: money may have moved, so the seller or admin has to answer the refund question. The reason is optional. |
| Seller | Anything up to `packed` | Needs a reason of ≥ 10 characters (`422 reason_required`). After shipping → `403 cancel_not_allowed`. |
| Admin | Anything non-terminal | A reason of ≥ 10 characters once past `pending`. Cancelling a shipped parcel does **not** restock. |

- **Claimed but unconfirmed:** the customer said they paid and nobody confirmed it. The canceller must send `payment_received`, otherwise `422 payment_received_required`:
  - `true` marks the payment `paid`, so a refund is due.
  - `false` stamps `payment_reported_missing_at`, and both sides see "payment reported as not received".
- Cancelling restocks the items unless the parcel had already shipped.

---

## 6. Admin tools

- **Rewinds** (`POST /admin/orders/{id}/rewind`) for courier orders are `paid → accepted`, `packed → paid` and `dispatched → paid | packed`. They never go back before the customer's acceptance.
  - Leaving `paid` reopens the payment and clears the ETA dates.
  - Leaving `dispatched` clears the tracking.
  - The seller hub's orders tab offers exactly one step back.
- **Force deliver:** `transition` to `delivered` with a reason. The seller and the customer are told.
- **Refund marker:** `POST /admin/orders/{id}/refund`. Use it only once the seller confirms the refund.
- **Refused for courier:** the delivery-address override (`409 not_applicable_for_courier`) and returns (`not_returnable_courier`).
- **List filters** (`GET /orders`):
  - `delivery_mode=courier`;
  - `needs=quote` — pending;
  - `needs=payment_check` — accepted, with a claim;
  - `needs=refund` — cancelled and still paid;
  - `stale=true` — nothing has happened for `COURIER_STALE_DAYS`.

  The operator lists expose these as chips (§10).

---

## 7. Settings

| Setting | Model | Changed by |
|---|---|---|
| Courier radius | `Store.courier_radius_km` (NULL = off; when set, larger than the local radius and ≤ `COURIER_MAX_RADIUS_KM`) | Store-basics change request (approved sellers). Pending sellers and admins write it directly with `PATCH /stores/{id}`. |
| Ship by courier, per service | `SellerProfileService.courier_enabled` | Services change request (approved sellers). Direct writes: `PATCH /sellers/me/services/{id}` (pending) and `PATCH /sellers/admin/{seller_id}/services/{id}` (admin). |
| Bank transfer | `SellerProfile.bank_account_name`, `bank_transfer_enabled` (plus the existing number and IFSC) | Banking change request |

Change-request payloads treat these optional fields as **omitted = unchanged**:

- `courier_radius_km: 0` turns the courier radius off;
- `bank_account_name: ""` clears the name;
- the canonical `proposed_json` stores `null` for anything omitted.

The radius rules (`422 courier_radius_not_larger` / `courier_radius_too_large`) and bank-transfer completeness (`422 bank_transfer_incomplete`) are checked at submission **and again at approval**.

---

## 8. Notifications and reminders

Courier-only events go through `services/courier_comms.py`, with copy in `services/courier_copy.py` and a single `courier_update` email template. Generic status changes (packed, dispatched, delivered, cancelled) keep using `record_and_dispatch_notification`, which picks courier wording via `render_status`. Customers get an in-app row plus Web Push; sellers get an in-app row (`NotificationType.SellerOrderUpdate`). Email and WhatsApp are added per event:

| To | Event | Email | WhatsApp |
|---|---|---|---|
| Customer | `quote_ready` | ✓ | ✓ (`COURIER_STATUS_TEMPLATES`) |
| Customer | `quote_revised`, `payment_not_received`, `payment_confirmed`, `auto_paid`, `refund_sent`, `reminder_quote`, `reminder_payment`, `reminder_arrival` | ✓ | |
| Customer | `tracking_updated` | | |
| Seller | `accepted`, `accepted_paid`, `payment_claimed`, `customer_received`, `payee_missing`, `reminder_quote`, `reminder_payment_check`, `reminder_overdue`, `reminder_refund` | ✓ | |
| Seller | `customer_cancelled` (the generic cancellation email already reaches them) | | |

**Reminders** come from the hourly `courier.send_reminders` beat task (minute 17). It sends only between `COURIER_QUIET_END_HOUR` and `COURIER_QUIET_START_HOUR` IST (09:00–21:00), never changes state, and sends one reminder per stage key (`order_courier.last_reminder_key`). It skips rows a live request holds (`FOR UPDATE SKIP LOCKED`), and stamps and commits each row before queueing its messages, so a crash can lose a reminder but never double it.

| Stage key | When | Who is nudged |
|---|---|---|
| `pending` | no quote `COURIER_REMINDER_HOURS` after placing | seller |
| `quoted:v{n}` | quote v*n* unanswered for `COURIER_REMINDER_HOURS` | customer |
| `accepted:r{n}` | accepted (or last claim rejected) and no claim for `COURIER_REMINDER_HOURS` | customer |
| `claimed:r{n}` | claim unanswered for `COURIER_REMINDER_HOURS` | seller |
| `overdue` | still `dispatched` more than `COURIER_ARRIVAL_GRACE_DAYS` after `eta_to` | customer and seller |
| `refund:{d}` | cancelled + paid for each of `COURIER_REFUND_REMINDER_DAYS` (1, 3, 7) | seller |

---

## 9. Error codes

Every code maps 1:1 to an `Errors.<code>` message in all five catalogs (`frontend/src/lib/errors.ts` `COURIER_ERROR_CODES`).

| Code | HTTP | When |
|---|---|---|
| `courier_unavailable` | 409 | The service no longer ships by courier (switched off, radius removed) |
| `courier_destination_unsupported` | 422 | The address isn't in India or has no 6-digit PIN |
| `address_within_local_area` | 422 | The address is inside the local radius now; place a normal order |
| `outside_courier_area` | 422 | The address is outside the courier ring now |
| `recipient_name_required` | 422 | Courier order without a recipient name |
| `invalid_recipient_phone` | 422 | The recipient phone isn't a +91 mobile |
| `courier_fields_not_allowed` | 422 | Recipient or tracking fields sent for a non-courier order |
| `preferred_window_not_allowed` | 422 | A preferred delivery window sent for a courier order |
| `upi_unavailable` / `bank_transfer_unavailable` | 409 | The chosen payee isn't live |
| `courier_payment_unavailable` | 409 | No live payee at accept or claim (the seller is told once) |
| `quote_superseded` | 409 | The customer accepted an old quote version |
| `quote_locked` | 409 | Quote after acceptance |
| `too_many_quote_versions` | 409 | Over `COURIER_MAX_QUOTE_VERSIONS` |
| `not_awaiting_payment` | 409 | Claim, confirm or "not received" outside `accepted` |
| `payment_method_required` | 422 | Courier claim without `{method}` |
| `payment_settled` | 409 | The payment is already confirmed |
| `no_claim` | 409 | "Not received" with no claim to reject |
| `invalid_tracking_url` | 422 | Not https, no host, credentials embedded, or longer than 500 characters |
| `already_delivered` | 409 | A second "delivered" from any party |
| `payment_received_required` | 422 | Cancel with an unanswered claim and no `payment_received` |
| `refund_not_due` / `already_refunded` | 409 | Refund-sent when nothing is owed, or a second time |
| `not_returnable_courier` | — | Return eligibility reason (courier orders aren't returnable) |
| `not_applicable_for_courier` | 409 | Admin delivery-address override on a courier order |
| `courier_radius_not_larger` / `courier_radius_too_large` | 422 | Radius rules (settings and change requests) |
| `bank_transfer_incomplete` | 422 | Bank transfer turned on without the name, number and IFSC |
| `reason_required` | 422 | Seller cancel, or admin action, without a 10+ character reason |
| `cancel_not_allowed` | 403 | The role can't cancel at this stage (§5) |

---

## 10. Frontend map

All courier copy exists in **en, hi, mr, gu and pa**. The two operator-only English surfaces, the change-request modal and the review diff table, stay English like the rest of those files.

| Area | Files | What it does |
|---|---|---|
| Shared helpers | `src/lib/courier.ts` | Zones (`classifyAddressZone`, `isOrderableZone`), `courierChargePending`, `customerActionNeeded`, `previewEtaWindow`, `latestQuote`, `trackingHost`, `straightLineKm` |
| API calls | `src/lib/orders.ts` | `sendCourierQuote`, `acceptCourierQuote`, `claimCourierPayment`, `confirmCourierPayment`, `rejectCourierPayment`, `updateCourierTracking`, `markCourierReceived`, `markRefundSent`, `cancelOrder(…{reason, paymentReceived})`, `refetchIfStale` (re-reads the order after a 403/409) |
| Status display | `OrderStatusBadge` (customer sees "Quote ready", operators "Quote sent"), `OrderTimeline` (Requested → Quote → Paid → Packed → Shipped → Delivered), `PaymentStatusPill` / `PaymentStatusBadge` ("Refund due"), `OrderTotal` (`₹X + courier`), `OrderCard` ("Action needed") | |
| Checkout | `checkout/[storeId]/[serviceId]/page.tsx`, `AddressPicker` (per-address zone badges and recheck), `PaymentMethodPicker` (courier branch), `courier/CourierExplainer`, `courier/RecipientFields` | Courier mode follows the picked address. It hides the route map, preferred window, ETA and price comparison, sends recipient details, and re-classifies addresses when the server says a zone changed (`zoneRecheck`). |
| Customer order page | `account/orders/[id]/page.tsx`, `courier/CourierQuoteCard`, `courier/CourierPayPanel` (UPI QR or bank tabs, "I've paid"), `courier/CourierSummary`, `courier/CourierCustomerActions` | Accept or decline the quote, pay, track, "I've received it", rate. No return entry. |
| Seller order page | `seller/orders/[id]/page.tsx`, `courier/CourierSellerActions`, `courier/CourierCancelDialog` | Quote and revise, payment received / not received, pack, ship with tracking, edit tracking, deliver, refund sent, cancel with the payment question |
| Admin | `admin/orders/[id]/page.tsx` (`courier/CourierAdminActions`), `admin/sellers/[id]/orders/page.tsx` (per-mode rewinds; courier cancels open `CourierCancelDialog`), `admin/orders/page.tsx` | Force deliver, refund marker, cancel; chips for **Courier**, **Waiting 3+ days** and **Refunds due** |
| Operator lists | `seller/orders/page.tsx` | Chips for **Needs quote**, **Check payment** and **Refunds due** |
| Settings | `seller/profile/page.tsx`, `ProfileChangeRequestModal`, `ChangeRequestDiffTable`, `admin/sellers/[id]/profile/page.tsx` | Courier radius (shown, edited via change request), per-service courier switch, bank transfer, a no-payee warning; the admin's direct switch |
| Dashboard | `seller/OrderStatusDonut` (courier segments listed only while non-zero), `seller/AttentionBanner` | |
| Discovery hints | `src/lib/useCourierZones.ts`, `stores/[id]/page.tsx` (courier banner listing services that don't ship), `cart/page.tsx` (courier hint instead of the fee nudge) | A preview for the navbar location, only when the customer actually chose one. The checkout address decides the real mode. |
| Shared UI | `UpiQrBlock` | QR, UPI ID and pay-with-app, extracted from `UpiPayPanel`, which now never renders for courier orders |

---

## 11. Data model

Migration `4675f7be7055_courier_delivery` (see `schema.sql`) adds:

- **`courier_quote`:**
  - `order_id`, `version`, `courier_fee`, `eta_min_days`, `eta_max_days`, `carrier_name`, `note`, `created_by_user_id`;
  - unique `(order_id, version)`.
- **`order_courier`**, one row per courier order:
  - recipient name and phone, `apply_store_credit`;
  - `accepted_quote_id` / `accepted_at`, `eta_from` / `eta_to`;
  - claim rejection (`payment_claim_rejected_at` / `_note` / `_count`);
  - tracking (`carrier_name`, `tracking_number`, `tracking_url`, `tracking_updated_at`), `delivered_by`;
  - cancellation (`cancel_reason`, `cancelled_by`, `cancelled_at`, `payment_reported_missing_at`);
  - `last_reminder_key` / `_at`.
- **New columns:**
  - `store.courier_radius_km`;
  - `sellerprofile_service.courier_enabled`;
  - `sellerprofile.bank_account_name`, `bank_transfer_enabled`;
  - `payment.refunded_at`, `refund_reference`, `refunded_by_user_id`.
- **Enum values:** `orderstatus` gains `Quoted` and `Accepted`, `deliverymode` gains `Courier`, and `notificationtype` gains `SellerOrderUpdate`.

---

## 12. Configuration

All optional, with safe defaults. Counts are `ge=1`, so a `0` fails startup instead of silently breaking the feature.

| Variable | Default | Meaning |
|---|---|---|
| `COURIER_MAX_RADIUS_KM` | 3500 | Largest courier radius a store may set |
| `COURIER_MAX_QUOTE_VERSIONS` | 5 | Quote revisions per order |
| `COURIER_REMINDER_HOURS` | 24 | Wait before each "still waiting" reminder |
| `COURIER_ARRIVAL_GRACE_DAYS` | 1 | Days past `eta_to` before the overdue nudge |
| `COURIER_REFUND_REMINDER_DAYS` | `[1,3,7]` | Days after a paid cancel to remind the seller to refund (JSON list) |
| `COURIER_STALE_DAYS` | 3 | Age for the admin "Waiting 3+ days" filter |
| `COURIER_QUIET_START_HOUR` / `COURIER_QUIET_END_HOUR` | 21 / 9 | Reminders go out only between 09:00 and 21:00 IST |

The frontend's quote-limit hint (5) and the change-request modal's radius cap (3,500 km) mirror these defaults. The server stays the authority if ops change them.

---

## 13. Deploying

- **No new secrets or env vars** are required; every setting above has a default.
- The GitHub Actions deploy already runs the `kb-migrate` Cloud Run job **before** rolling the API, web and VM worker. Migration `4675f7be7055` therefore lands first, and the new enum values and columns exist before any new code reads them. When deploying by hand, keep that order: migrate, then API and worker.
- The VM worker runs `celery … worker --beat`, so the new `courier-reminders-hourly` schedule is picked up when the deploy restarts the worker. `/opt/kb/.env` needs no change.
- Existing stores are unaffected until a seller sets a courier radius, switches a service on, and has a live payee.
- Dev seed: one Mumbai store (Krishna Supermart, `seller2@khanabazaar.dev`) ships by courier with a 1,500 km radius and bank transfer on. The demo customer's "Pune Trip" address falls inside that ring.

---

## 14. Testing

- **Backend:** `backend/app/tests/test_courier_*.py` (17 files, shared helpers in `tests/_courier_helpers.py`) cover models, config, zones, settings and change requests, checkout, quotes, accept, payment, shipping, cancel and refund, admin, list filters, notifications, reminders and the dev seed. Run them like the rest of the suite (`uv run pytest -q`). The memory notes in `CLAUDE.md` explain why to give a concurrent run its own `KB_TEST_DB`, Redis db and Meilisearch.
- **Frontend:** there are no frontend tests in this repo. `npm run lint`, `npx tsc --noEmit`, `npm run check:i18n` and `npm run build` must pass, and the flows were walked in a browser against a private seeded database.

---

## 15. Known limitations (Phase A)

- **Payment is off-platform.** The app records claims and confirmations; it never moves money. Refunds are recorded, not executed.
- **Tracking is manual.** There's no carrier integration: the seller pastes the carrier, number and link.
- **Courier stores are reached by link.** Store listings and search still show local stores only. Discovery is Phase B; the store-page banner and cart hint are Phase A's bridge.
- **Notification copy is English-only,** like every message in the repo. The UI is translated.
- **No returns.** If a parcel comes back, the seller restocks it by hand.
