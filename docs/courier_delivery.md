# Courier delivery (long-distance orders)

Courier delivery lets a store ship to customers **beyond its local delivery radius**, up to a courier radius it sets. The seller only knows the real courier charge once they see the parcel and the destination, so the flow is quote-first:

> customer places the order (no delivery charge yet) → seller quotes the courier charge and the delivery time → customer accepts → customer pays the seller directly (UPI or bank transfer) → seller confirms the money → seller packs and ships, with optional tracking → delivered.

There is **no delivery OTP**, payment is **prepaid only**, tracking is **optional**, and courier orders **cannot be returned** in the app.

This page is the reference for the whole feature: backend rules, API, error codes, frontend screens, configuration and deploy notes. The step-by-step request flow also lives in [`flows.md` §13](flows.md#13-courier-orders-long-distance-delivery), and the condensed gotchas live in `CLAUDE.md` under *Courier orders*. The design spec and the implementation plans (Phase A and Phase B) are worktree-local working documents (`docs/superpowers/` is gitignored), so this page is meant to stand on its own.

---

## 1. Who can use it

An address can take a courier order from a store only when **all** of these hold:

| Rule | Where it lives |
|---|---|
| The address is beyond `Store.delivery_radius_km` but within `Store.courier_radius_km` (the courier ring). | `services/serviceability.py` (`zone_for_point`, PostGIS `ST_DWithin`) |
| The service has `SellerProfileService.courier_enabled = true`. | same |
| The seller is **approved** and has a **live prepaid payee**: UPI (`upi_enabled` + `upi_vpa`), or bank transfer (`bank_transfer_enabled` + account name + account number + IFSC). Rejecting a seller darkens their payees in listings (`_PAYEE_LIVE_SQL`) and on placed orders. | `serviceability.courier_payment_methods` |
| The point is inside the India bounding box. At checkout the saved address must also have `country == "India"` and a 6-digit PIN, because the box (6.5–36° N, 68–98° E) also takes in neighbouring countries (Pakistan, Afghanistan's east, Nepal, Bhutan, Bangladesh, Sri Lanka, Tibet and western China, most of Myanmar). | `serviceability.is_courier_destination`, `checkout.py` |
| The store and service are not paused, and the seller is approved. | Enforced at checkout and in listings exactly as for local orders. Zones carry no availability rules. |

`services/serviceability.py` is the **only** home of the radius rule:

- listing queries build on its SQL fragments (`LOCAL_SQL`, `zone_case_sql`);
- door checkout and the admin delivery-address override use the status-blind `within_local_radius`: door checkout reports an inactive store as `store_unavailable` in a later check, and the override never looked at store status, so both behave as before;
- search reads a cached per-point `Locality`;
- single-store checks use `zone_for_point`.

Checkout's "cheaper at another store" comparison uses `LOCAL_SQL` and stays local-only.

`POST /api/v1/geo/serviceability` with a `store_id` returns:

- `serviceable`, which keeps its **local-only** meaning so older callers are unaffected (this is the API field; the checkout address picker's own notion of an orderable address covers local *or* courier);
- `zone`: `local` | `courier` | `none`;
- `courier_service_ids`: the services that can ship there. Without `service_id`, `zone: "courier"` means *some* service ships. With `service_id`, it means *that* service does.

Without a `store_id` (count mode) it returns `store_count` (local stores) and `courier_store_count` (stores that ship there by courier).

### Discovery (Phase B)

Every listing shows local results first, then courier ones, and tags each row `fulfilment: local | courier | null`.

| Surface | Behaviour |
|---|---|
| `GET /stores/?lat&lng` | Local stores, then courier stores, each by distance (or id). Courier rows carry `courier_service_ids`. A `?service=` filter needs that service to ship for a courier row; a `radius_km` cap applies to distance in both zones. Without a location the list is unchanged and `fulfilment` is null. |
| Count mode (above) | The `courier_only` state on Home, Stores and Products is 0 local stores and at least 1 courier store. |
| Locality cache (`search/locality.py`) | `get_locality` returns `Locality{local, courier: {service_id: [store_ids]}}`, cached per ~500 m cell for `SEARCH_SERVICEABLE_GRID_TTL_SECONDS` under the **`serviceable:v2:`** prefix. v1 held a bare list of local ids, so a deploy never reads one back. `get_serviceable_store_ids` remains as the local-only view. |
| `GET /search/products` | Two disjoint queries: ① `store_ids IN [local]`; ② per service, `(service_id = S AND store_ids IN [courier_S])`, minus anything a local store sells. `search/partition.stitched_search` counts each group exactly (`page=1, hits_per_page=0`), places the page window across ① then ②, and sums the facets. The user's sort applies within each group. Offers carry `fulfilment`, `is_serviceable` means orderable here (local or courier), and offers list local → courier → can't reach. A `store_id`-scoped search is unchanged. |
| `GET /search/suggest` | Products: ① first, ② fills up to the limit. `store_count` and the best store count only stores that reach the point; the best store is in stock first, then local before courier, then cheapest, and carries `fulfilment`. Stores: local → courier → every other store, each with `fulfilment`. When nothing at all serves the point, suggest returns an empty response (no stores either); `/search/stores` still lists every store. |
| `GET /search/stores` | The same three store groups, stitched across pages with an exact `total`. |
| `GET /search/browse` | Each category carousel lists local products, then courier ones; subcategory chips count both groups. The courier group carries only this service's courier stores. With no local store and no courier store for the service it returns no categories straight away; otherwise categories with no matching products are dropped. |
| `GET /search/products/{id}/stores` | Offers carry `fulfilment`, ordered local → courier → can't reach, cheapest first within each. Without a location: cheapest first, as before. |
| `GET /favorites/` | A favourite a local store sells stays under that store only. One that only a courier store ships (for the product's own service) moves from "unavailable" into that store's group (`fulfilment: "courier"`), after the local groups. |

---

## 2. Lifecycle

```
pending ──quote──▶ quoted ──accept──▶ accepted ──confirm payment──▶ paid ──▶ packed ──▶ dispatched ──▶ delivered
   │      (revise: stays quoted)         │  ▲                                    │            │
   │                                     │  └── "not received" (claim cleared)   │            │
   └──────────────── cancelled ◀─────────┴───────────────────────────────────────┴────────────┘
```

- Courier orders use their own transition table, `services/courier_rules.COURIER_TRANSITIONS`. Door delivery and pickup keep `LEGAL_TRANSITIONS`, and `transition_order_status` picks the table per mode.
- `OrderStatus.Paid` was defined but never used before. For courier it means the money is settled: the seller confirmed it, the ₹0 auto-pay at acceptance set it, or an admin rewound to `paid` (from `packed` or `dispatched`).
- `OrderStatus.Quoted` and `OrderStatus.Accepted` are new. Both count as **active** (`ACTIVE_ORDER_STATUSES`), so they show in "active" lists and block account deactivation like any open order.
- Every courier action, plus `transition`, `cancel`, the admin rewind and the admin refund marker, takes a `SELECT … FOR UPDATE` on the order (`courier_rules.lock_order`), so concurrent taps serialise. `tests/test_courier_races.py` pins three races with two real sessions: revise vs accept, cancel vs confirm, and seller vs customer marking delivered.

| Step | Who | Endpoint | Result |
|---|---|---|---|
| Place | Customer | `POST /orders` with `delivery_mode: "courier"`, `recipient_name`, `recipient_phone` | `pending`, `delivery_fee = 0`, stock reserved, store credit covers the goods |
| Quote / revise | Seller (own store) | `POST /orders/{id}/courier/quote` | `quoted`; append-only versions. Repeating the latest quote unchanged within 60 seconds (a double tap or a network retry) returns it without a new version or a new message. |
| Accept | Customer (owner) | `POST /orders/{id}/courier/accept` `{quote_id}` | `accepted`, or `paid` when ₹0 is payable |
| "I've paid" | Customer (owner) | `POST /orders/{id}/payment/claim` `{method}` | stamps `payment.customer_claimed_at`; status unchanged |
| Payment received | Seller | `POST /orders/{id}/payment/confirm` | `paid`; fixes `eta_from` / `eta_to` |
| Not received | Seller | `POST /orders/{id}/payment/not-received` `{note?}` | clears the claim and records the note; still `accepted` |
| Pack | Seller / admin | `POST /orders/{id}/transition` `{to: "packed"}` | `packed` |
| Ship | Seller / admin | `POST /orders/{id}/transition` `{to: "dispatched", carrier_name?, tracking_number?, tracking_url?}` | `dispatched`; **no OTP issued**. A carrier left out defaults to the one on the accepted quote; `carrier_name: ""` means none. |
| Edit tracking | Seller (own store), while `dispatched` | `PATCH /orders/{id}/courier/tracking` | omitted = unchanged, `""` = clear |
| Deliver | Seller (`transition` → `delivered`), customer (`POST /orders/{id}/courier/received`), or admin (`transition` with `reason`) | | `delivered`; `order_courier.delivered_by` records who |
| Refund sent | Seller | `POST /orders/{id}/payment/refund-sent` `{reference?}` | stamps `payment.refunded_at`, sets `refunded` |

---

## 3. Money

- **Quotes are append-only** (`courier_quote`). The limit is `COURIER_MAX_QUOTE_VERSIONS` versions (default 5), after which you get `409 too_many_quote_versions`. Customers see only the latest version; sellers and admins see them all.
- **Accept names the version the customer saw** (`quote_id`). If the seller revised the quote in the meantime → `409 quote_superseded`, and the page shows the new quote. Accepting the same version twice is a no-op.
- On accept:
  - the charge is copied into `Order.delivery_fee`, and `Order.total` is recalculated;
  - if the customer left "use store credit" on at checkout, store credit **tops up** as a second ledger entry, so credit they still hold at that store also goes toward the courier charge;
  - `Payment.amount` becomes `total − store_credit_applied`, the net amount payable.
  - Cancelling later reverts both credit entries (`revert_order(store_credit_applied)`).
- **₹0 payable** (store credit covered everything) skips straight to `paid`, and the customer is told.
- **Order-value fees:** the courier charge is **excluded** from the platform's order-value % fee. Courier rows use `total − delivery_fee` (`fee_order_value.compute_order_value_sales`).
- **Refunds:** cancelling after the money arrived leaves `Payment.status = paid`. On a cancelled order, `Paid` **with a non-zero amount** is the "refund due" state (`OrderRead.courier.refund_due`). One rule, `courier_rules.refund_owed`, drives the read model, the `needs=refund` filter, the reminders and refund-sent; the in-app copy checks the same paid-and-above-₹0 condition itself, and the emails' refund line only renders a non-zero amount. A ₹0 payment (store credit covered everything) owes nothing: the credit goes back as credit on cancel, and both refund-sent and the admin refund marker answer `409 refund_not_due`. The refund ends when either:
  - the seller records `payment/refund-sent`, with an optional UTR reference; or
  - an admin uses the refund marker (`POST /admin/orders/{id}/refund`).

  Both stamp `refunded_at` and `refunded_by_user_id`. The usual "Paid → Refunded on cancel" flip is skipped for courier.
- Before acceptance the courier charge is **not** in `Order.total`. Every list and total therefore renders `₹X + courier` while the order is `pending` or `quoted` (frontend `courierChargePending`).

---

## 4. Payment

- **Prepaid only.** The method is `upi` or `net_banking` (labelled "Bank transfer"). Cash, pay-at-store and postpaid credit are all refused. At checkout the method is a *preference*; the customer can pay by any live method once they accept.
- Bank details (`OrderRead.courier.bank_transfer`) are exposed **only to the owning customer, only while the order is `accepted`**. Since the payment-settings work (spec 2026-10-07) they come from the payee saved on the order at placement — every live prepaid method is saved — unless the seller switched that method off since; the pay panel reads `OrderRead.payee` and `courier.bank_transfer` carries the same value for older clients.
- `payable_methods` lists the methods that are live right now. If every payee disappears after acceptance:
  - accept and claim answer `409 courier_payment_unavailable`;
  - the seller is told once (`payee_missing`);
  - the customer's pay panel says the store can't take payments yet.
- **Claim:** the customer must send `{method}` (`422 payment_method_required` otherwise; `422 payment_method_not_allowed` for anything but `upi` / `net_banking`). The seller is notified once per claim round; switching method after claiming is recorded silently (the seller's screen shows the current method), and a rejected claim starts a new round.
- **Confirm** works before a claim too, for a seller who sees the money arrive first. It fixes `eta_from` and `eta_to` as IST today plus the quoted days.
- **Not received** needs a claim (`409 no_claim`). It clears the claim and shows the seller's note to the customer, who can check and pay again. Each rejection bumps `payment_claim_rejection_count`, which starts a new reminder stage.

---

## 5. Cancelling

| Who | Allowed | Notes |
|---|---|---|
| Customer | `pending`, `quoted` (declining the quote), and `accepted` **until they tap "I've paid"** | After a claim → `403 cancel_not_allowed`: money may have moved, so the seller or admin has to answer the refund question. The reason is optional. |
| Seller | Anything up to `packed` | Needs a reason of ≥ 10 characters (`422 reason_required`). After shipping → `403 cancel_not_allowed`. |
| Admin | Anything non-terminal | A reason of ≥ 10 characters once past `pending`. Cancelling a shipped parcel does **not** restock. Unlike door/pickup orders, this works even after the seller lost approval (spec §9.9), and so does the refund marker; every other admin fulfilment action (pack, ship, force-deliver, rewind) still answers `409 seller_not_active`. |

- **Claimed but unconfirmed:** the customer said they paid and nobody confirmed it. The canceller must send `payment_received`, otherwise `422 payment_received_required`:
  - `true` marks the payment `paid`, so a refund is due.
  - `false` stamps `payment_reported_missing_at`, and both sides see "payment reported as not received".
- Cancelling restocks the items unless the parcel had already shipped.

---

## 6. Admin tools

- **Rewinds** (`POST /admin/orders/{id}/rewind`) for courier orders are `paid → accepted`, `packed → paid` and `dispatched → paid | packed`. They never go back before the customer's acceptance.
  - Leaving `paid` reopens the payment and clears the ETA dates.
  - Leaving `dispatched` clears the tracking.
  - The seller hub's orders tab offers exactly one step back, and its confirmation spells out these side effects.
- **Force deliver:** `transition` to `delivered` with a reason. The seller and the customer are told.
- **Refund marker:** `POST /admin/orders/{id}/refund`. Use it only once the seller confirms the refund.
- **Refused for courier:** the delivery-address override (`409 not_applicable_for_courier`) and returns (`409 not_returnable_courier`).
- **List filters** (`GET /orders`):
  - `delivery_mode=courier`;
  - `needs=quote` — pending;
  - `needs=payment_check` — accepted, with a claim;
  - `needs=refund` — cancelled, still paid, amount above ₹0;
  - `stale=true` — `pending`, `quoted` or `accepted` with no movement for `COURIER_STALE_DAYS` (placing, the latest quote, acceptance, a rejected claim or a claim), or `dispatched` and more than `COURIER_ARRIVAL_GRACE_DAYS` past `eta_to`. `paid` and `packed` orders never count (see §15).

  The operator lists expose these as chips (§10). The "Refunds due" chips sort oldest first by order date (cancellation time isn't a sortable column).

---

## 7. Settings

| Setting | Model | Changed by |
|---|---|---|
| Courier radius | `Store.courier_radius_km` (NULL = off; when set, larger than the local radius and ≤ `COURIER_MAX_RADIUS_KM`) | Store-basics change request (approved sellers). Pending sellers write it directly with `PATCH /stores/{id}`. Admins have no direct route: they change it by approving a change request with edits (the review form exposes `courier_radius_km` for store-basics requests; empty = unchanged, 0 = off). |
| Ship by courier, per service | `SellerProfileService.courier_enabled` | Services change request (approved sellers). Direct writes: `PATCH /sellers/me/services/{id}` (pending) and `PATCH /sellers/admin/{seller_id}/services/{id}` (admin, audited). |
| Bank transfer | `SellerProfile.bank_account_name`, `bank_transfer_enabled` (plus the existing number and IFSC) | Details: banking change request (approved sellers). The switch: instant on the seller's Payments page (`PATCH /sellers/me/payments/methods`, details must already be approved) or the admin hub's Payments tab; it is store-wide, so it also offers bank transfer on door-delivery and pickup orders. Pending sellers write both with `PATCH /sellers/me/profile` or at signup. |

Change-request payloads treat these optional fields as **omitted = unchanged**:

- `courier_radius_km: 0` turns the courier radius off;
- `bank_account_name: ""` clears the name;
- the canonical `proposed_json` stores `null` for anything omitted.

The radius rules (`422 courier_radius_not_larger` / `courier_radius_too_large`) and bank-transfer completeness (`422 bank_transfer_incomplete`) are checked at submission **and again at approval**. The cap (`courier_radius_too_large`) binds only a ring that differs from the stored one, so lowering `COURIER_MAX_RADIUS_KM` below a store's existing ring never blocks an unrelated edit: a pin confirmation, or a local-radius change whose pre-filled form re-sends the existing ring unchanged (the change-request modal applies the same rule before submitting). "Larger than the local radius" is checked against the merged values whenever either radius changes.

A change request submitted before this release lacks the new keys. Approval compares the applied values with the stored proposal **re-validated into today's shape** (`schemas.seller_profile_change_request.normalize_group_payload`), so approving such a request untouched is a plain approval, not "approved with edits", in both the audit log and the seller's email.

---

## 8. Notifications and reminders

Courier-only events go through `services/courier_comms.py`, with copy in `services/courier_copy.py` and a single `courier_update` email template. Generic status changes (packed, dispatched, delivered, cancelled) keep using `record_and_dispatch_notification`, which picks courier wording via `render_status`. Customers get an in-app row plus Web Push; sellers get an in-app row (`NotificationType.SellerOrderUpdate`). Email and WhatsApp are added per event:

| To | Event | Email | WhatsApp |
|---|---|---|---|
| Customer | `quote_ready` | ✓ | ✓ (`COURIER_EVENT_TEMPLATES`) |
| Customer | `quote_revised`, `payment_not_received`, `payment_confirmed`, `auto_paid`, `refund_sent`, `reminder_quote`, `reminder_payment`, `reminder_arrival` | ✓ | |
| Customer | `tracking_updated` | | |
| Seller | `accepted`, `accepted_paid`, `payment_claimed`, `customer_received`, `payee_missing`, `reminder_quote`, `reminder_payment_check`, `reminder_overdue`, `reminder_refund` | ✓ | |
| Seller | `customer_cancelled` (the generic cancellation email already reaches them) | | |

Generic status messages for courier orders:

- **Shipped:** the email names the carrier and tracking number and links the tracking page when the seller gave one; WhatsApp uses `courier_shipped` (`COURIER_STATUS_TEMPLATES`).
- **Cancelled after the money arrived:** the customer's copy says the store owes them ₹X; the seller's copy says "You owe the customer a refund of ₹X … tap Refund sent". An **admin** cancel sends the admin-action emails instead, and both carry the same refund line (door/pickup keep their old wording).
- **New order:** the seller's SMS and WhatsApp alert say "New courier order … + courier … send a courier quote" (`seller_new_courier_order`), since the total is goods only until the quote.

Differences from the spec's messaging table, all deliberate:

- In-app rows use `status_value = courier_<event>` (generic statuses keep their plain value), and reminders are split per stage (`courier_reminder_quote`, …) rather than one `courier_reminder`. Both bells render the stored title and body; the backend only reads the value to send `payee_missing` once per order.
- A revised quote sends no WhatsApp (only the first quote has a template).
- There is one generic `courier_update` email template filled from `courier_copy`, not one per event.
- Queued email and WhatsApp tasks read the order when they run, so a message can reflect a later state (for example, a "payment not received" email sent after the customer already claimed again shows no note).

**Reminders** come from the hourly `courier.send_reminders` beat task (minute 17 UTC, which is :47 IST, so the first daytime run is 09:47). Quiet hours are `[COURIER_QUIET_START_HOUR, COURIER_QUIET_END_HOUR)` IST, 21:00–09:00 by default. The window may wrap midnight or not (`0` → `7` keeps only 00:00–06:59 quiet), and START == END means no quiet hours. The sweep never changes state and sends one reminder per stage key (`order_courier.last_reminder_key`). It skips rows a live request holds (`FOR UPDATE SKIP LOCKED`), and stamps and commits each row before queueing its messages, so a crash can lose a reminder but never double it. The customer's "accept your quote" and "please pay" nudges are held back while the store has no live payee (accepting or paying would fail), and go out once one is back.

| Stage key | When | Who is nudged |
|---|---|---|
| `pending` | no quote `COURIER_REMINDER_HOURS` after placing | seller |
| `quoted:v{n}` | quote v*n* unanswered for `COURIER_REMINDER_HOURS` | customer |
| `accepted:r{n}` | accepted (or last claim rejected) and no claim for `COURIER_REMINDER_HOURS` | customer |
| `claimed:r{n}` | claim unanswered for `COURIER_REMINDER_HOURS` | seller |
| `overdue` | still `dispatched` more than `COURIER_ARRIVAL_GRACE_DAYS` after `eta_to` | customer and seller |
| `refund:{d}` | cancelled with a refund owed; `d` is the latest of `COURIER_REFUND_REMINDER_DAYS` (1, 3, 7) reached. A sweep that missed a day sends only the latest one, so at most one reminder per day reached. | seller |

---

## 9. Error codes

Every code maps to an `Errors.<code>` message in all five catalogs (`frontend/src/lib/errors.ts` `apiErrorKey`; most go through `COURIER_ERROR_CODES`, the shared ones through explicit checks).

| Code | HTTP | When |
|---|---|---|
| `courier_unavailable` | 409 | The service no longer ships by courier (switched off, radius removed) |
| `courier_destination_unsupported` | 422 | The address isn't in India or has no 6-digit PIN |
| `address_within_local_area` | 422 | The address is inside the local radius now; place a normal order |
| `outside_courier_area` | 422 | The address is outside the courier ring now |
| `recipient_name_required` | 422 | Courier order without a recipient name, or one over 120 characters |
| `invalid_recipient_phone` | 422 | The recipient phone isn't a +91 mobile |
| `courier_fields_not_allowed` | 422 | Recipient fields on a non-courier order, or tracking fields on any transition other than a courier `dispatched` |
| `preferred_window_not_allowed` | 422 | A preferred delivery window sent for a courier order |
| `upi_unavailable` / `bank_transfer_unavailable` | 409 | The chosen payee isn't live |
| `courier_payment_unavailable` | 409 | No live payee at accept or claim (the seller is told once) |
| `quote_superseded` | 409 | The customer accepted an old quote version |
| `quote_locked` | 409 | Quote after acceptance |
| `too_many_quote_versions` | 409 | Over `COURIER_MAX_QUOTE_VERSIONS` |
| `not_awaiting_payment` | 409 | Claim outside `accepted` (confirm answers `payment_settled` or `illegal_transition` instead; "not received" answers `no_claim` or `illegal_transition`) |
| `payment_method_required` | 422 | Courier claim without `{method}` |
| `payment_method_not_allowed` | 422 | Courier checkout or claim with a non-prepaid method (cash, credit, pay at store); an unknown value gets FastAPI's generic 422 |
| `payment_settled` | 409 | The payment is already confirmed |
| `no_claim` | 409 | "Not received" with no claim to reject |
| `invalid_tracking_url` | 422 | Not https, no host, credentials embedded, or longer than 500 characters |
| `already_delivered` | 409 | A second "delivered" from any party |
| `payment_received_required` | 422 | Cancel with an unanswered claim and no `payment_received` |
| `refund_not_due` / `already_refunded` | 409 | Refund-sent when nothing is owed (also the admin refund marker on a ₹0 courier payment), or a second time |
| `not_returnable_courier` | 409 | Creating a return for a courier order (also the eligibility reason) |
| `not_applicable_for_courier` | 409 | Admin delivery-address override on a courier order |
| `courier_radius_not_larger` / `courier_radius_too_large` | 422 | Radius rules (settings and change requests) |
| `bank_transfer_incomplete` | 422 | Bank transfer turned on without the name, number and IFSC |
| `reason_required` | 422 | Seller cancel, or admin action, without a 10+ character reason |
| `cancel_not_allowed` | 403 | The role can't cancel at this stage (§5) |
| `not_a_courier_order` | 409 | A courier-only endpoint called on a door/pickup order |
| `not_dispatched` | 409 | Tracking edit on an order that isn't `dispatched` |
| `terminal_status` | 409 | Quoting, cancelling or rewinding a delivered or cancelled order |
| `illegal_transition` | 409 | Any step the courier table doesn't allow from the current status |
| `seller_not_active` | 409 | Any admin transition (pack, ship, force-deliver) or rewind once the seller lost approval |
| `outside_delivery_area` | 422 | Door delivery: the address left the store's local radius (the checkout re-classifies addresses) |

---

## 10. Frontend map

All courier copy exists in **en, hi, mr, gu and pa**. The two operator-only English surfaces, the change-request modal and the review diff table, stay English like the rest of those files.

| Area | Files | What it does |
|---|---|---|
| Shared helpers | `src/lib/courier.ts` | Zones (`classifyAddressZone`, `isOrderableZone`), `courierChargePending`, `customerActionNeeded`, `previewEtaWindow`, `latestQuote`, `trackingHost`, `straightLineKm`; discovery: `showsCourierBadge`, `storeServesService`, `localFirst`, `courierShippedServiceIds`, `deliverabilityCounts` |
| API calls | `src/lib/orders.ts` | `sendCourierQuote`, `acceptCourierQuote`, `claimCourierPayment`, `confirmCourierPayment`, `rejectCourierPayment`, `updateCourierTracking`, `markCourierReceived`, `markRefundSent`, `cancelOrder(…{reason, paymentReceived})`, `refetchIfStale` (re-reads the order after a 403/409) |
| Status display | `OrderStatusBadge` (customer sees "Quote ready", operators "Quote sent"), `OrderTimeline` (Requested → Quote → Paid → Packed → Shipped → Delivered), `PaymentStatusPill` / `PaymentStatusBadge` ("Refund due"), `OrderTotal` (`₹X + courier`), `OrderCard` ("Action needed") | The customer's **Active** filter includes `quoted`, `accepted` and `paid`, mirroring the server's `ACTIVE_ORDER_STATUSES`. |
| Checkout | `checkout/[storeId]/[serviceId]/page.tsx`, `AddressPicker` (per-address zone badges and recheck), `PaymentMethodPicker` (courier branch), `courier/CourierExplainer`, `courier/RecipientFields` | Courier mode follows the picked address. It hides the route map, preferred window, ETA and price comparison, sends recipient details, and re-classifies addresses when the server says a zone changed (`zoneRecheck`, including a door order's `outside_delivery_area`). The unavailable group is headed "Outside delivery area" only when every address in it really is out of range. The recipient phone accepts pasted or autofilled `+91 98765 43210`, `919876543210` and `09876543210`. |
| Customer order page | `account/orders/[id]/page.tsx`, `courier/CourierQuoteCard`, `courier/CourierPayPanel` (UPI QR or bank toggle buttons, "I've paid"), `courier/CourierSummary`, `courier/CourierCustomerActions` | Accept or decline the quote (focus then moves to the pay panel or the page heading), pay, track, "I've received it", rate. No return entry. Once the customer has claimed, the pay panel keeps showing the claim even if the store's payees disappear. |
| Seller order page | `seller/orders/[id]/page.tsx`, `courier/CourierSellerActions`, `courier/CourierCancelDialog` | Quote and revise (the cap comes from `courier.max_quote_versions`), payment received / not received, pack, ship with tracking (pre-filled with the quote's carrier; editing tracking shows only what is saved), edit tracking, deliver, refund sent, cancel with the payment question. The cancel dialog re-reads the order on `payment_received_required`, so a claim made while it was open turns into the "did ₹X reach you?" question. |
| Admin | `admin/orders/[id]/page.tsx` (`courier/CourierAdminActions`), `admin/sellers/[id]/orders/page.tsx` (per-mode rewinds; courier cancels open `CourierCancelDialog`; courier cancel and refund stay enabled after the seller lost approval), `admin/orders/page.tsx`, `admin/customers/[id]/orders/page.tsx` (courier label and `₹X + courier` via `AdminCustomerOrder.delivery_mode`) | Force deliver, refund marker, cancel (a failed reason modal stays open with the message); chips for **Courier**, **Stalled** (tooltip with `COURIER_STALE_DAYS`) and **Refunds due** |
| Operator lists | `seller/orders/page.tsx` | Chips for **Needs quote**, **Check payment** and **Refunds due**; a **Courier** tag beside the status; "Customer says paid" only while it is an open question (payment unconfirmed, and not a cancelled courier order, whose cancel already answered it) |
| Settings | `seller/profile/page.tsx`, `seller/payments/page.tsx`, `ProfileChangeRequestModal`, `ChangeRequestDiffTable`, `admin/sellers/[id]/profile/page.tsx`, `admin/sellers/[id]/payments/page.tsx` | Courier radius (shown, edited via change request; the cap and its hint come from `/meta/public-config`), per-service courier switch, a no-payee warning linking to Payments; bank transfer and UPI live on the Payments page (and the admin hub's Payments tab); the admin's direct courier switch. "Edit and resubmit" applies the omit/clear rules against `cr.baseline_json` (the live values), and the diff table treats a radius of 0 and none as the same "Off" and, against the live values, shows a proposed "off" for the UPI / bank switches as no change (approval only ever switches them on). |
| Dashboard | `seller/OrderStatusDonut` (courier segments listed only while non-zero), `seller/AttentionBanner` | The banner counts only orders waiting on the seller: pending, paid, packed, dispatched, plus claimed payments to confirm (`SellerMetricsRead.courier_payment_checks`). `quoted` and unclaimed `accepted` orders are the customer's turn. |
| Discovery (Phase B) | `src/lib/useDeliverability.ts`, `CourierOnlyBanner`, `CourierBadge`, Home (`[locale]/page.tsx`, `HomeStorePreview`), `stores/page.tsx`, `products/page.tsx`, `search/{SearchDropdown,SearchStoresRail,ProductOfferList}.tsx`, `search/product/[productId]/page.tsx`, `account/favorites/page.tsx` | `useDeliverability` adds `courier_only` (0 local stores, at least 1 courier store; `courierStoreCount`), where Home, Stores and Products show `CourierOnlyBanner` instead of the fallback; Products then opens on a service a courier store ships. `CourierBadge` (`Shared.courierBadge`) marks store cards, the home preview (titled `Home.previewTitleCourier`), search store rows, suggest's best store, compare offers and favourites groups, always through `showsCourierBadge(row, userSet)` so it never describes the Mumbai fallback. Preview candidates go local first (`localFirst`) and a courier store only for a service it ships (`storeServesService`). Lists keep the API's order (local first); no screen re-sorts. The compare page shows a result only for the location it was fetched for. |
| Arrival hints (Phase A) | `src/lib/useCourierZones.ts`, `stores/[id]/page.tsx` (courier banner listing services that don't ship), `cart/page.tsx` (courier hint instead of the fee nudge) | A preview for the navbar location, only when the customer actually chose one. The checkout address decides the real mode. Answers are cached for two minutes per location and store (failures never), since `/geo/serviceability` shares a 30-per-minute per-IP budget with checkout's address checks. |
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
| `COURIER_STALE_DAYS` | 3 | Age for the admin "Stalled" filter (`stale=true`) |
| `COURIER_QUIET_START_HOUR` / `COURIER_QUIET_END_HOUR` | 21 / 9 | Quiet hours `[START, END)` IST; may wrap midnight or not; equal values mean no quiet hours |

The frontend reads the limits from the server instead of hard-coding them: `OrderRead.courier.max_quote_versions` drives the "Revise quote" cap, and `GET /meta/public-config` carries `courier_max_radius_km` and `courier_stale_days` for the change-request modal and the admin chip tooltip. The server stays the authority either way.

---

## 13. Deploying

- **No new secrets or env vars** are required; every setting above has a default.
- The GitHub Actions deploy already runs the `kb-migrate` Cloud Run job **before** rolling the API, web and VM worker. Migration `4675f7be7055` therefore lands first, and the new enum values and columns exist before any new code reads them. When deploying by hand, keep that order: migrate, then API and worker.
- The VM worker runs `celery … worker --beat`, so the new `courier-reminders-hourly` schedule is picked up when the deploy restarts the worker. `/opt/kb/.env` needs no change.
- Existing stores are unaffected until a seller sets a courier radius, switches a service on, and has a live payee.
- Dev seed: one Mumbai store (Krishna Supermart, `seller2@khanabazaar.dev`) ships by courier with a 1,500 km radius and bank transfer on. The demo customer's "Pune Trip" address falls inside that ring.

---

## 14. Testing

- **Backend:** `backend/app/tests/test_courier_*.py` (18 files, shared helpers in `tests/_courier_helpers.py`) cover models, config, zones, settings and change requests, checkout, quotes, accept, payment, shipping, cancel and refund, admin, list filters, notifications, reminders, two-session races and the dev seed. Discovery lives in `tests/test_discovery_*.py` (world in `tests/_discovery_helpers.py`: a store local to Mysuru beside the courier world, plus opt-in extras for per-service and multi-product cases): zone SQL and `Locality` (including a parity matrix against `zone_for_point`), the moved callers, store-list ordering and filters, the counts, search partition across page boundaries, suggest and store-name ordering, browse, compare and favourites. The v2 cache is pinned in `tests/test_search_locality.py`. Run them like the rest of the suite (`uv run pytest -q`). A run that overlaps another needs its own database: set `KB_TEST_DB` (read in `backend/app/tests/conftest.py`), point `REDIS_URL` at a spare Redis db, and point `MEILI_TEST_URL` at its own Meilisearch.
- **Frontend:** there are no frontend tests in this repo. `npm run lint`, `npx tsc --noEmit`, `npm run check:i18n` and `npm run build` must pass, and the flows were walked in a browser against a private seeded database.

---

## 15. Known limitations

- **Payment is off-platform.** The app records claims and confirmations; it never moves money. Refunds are recorded, not executed.
- **Tracking is manual.** There's no carrier integration: the seller pastes the carrier, number and link.
- **The India box is wider than India.** Discovery decides courier reach from the map point, and the box (6.5–36° N, 68–98° E) also takes in neighbouring countries (Pakistan, Afghanistan's east, Nepal, Bhutan, Bangladesh, Sri Lanka, Tibet and western China, most of Myanmar), so a point there can list courier stores. Checkout still refuses the address (country and PIN).
- **Discovery ignores availability by design, and "sold locally" means two things.** Search groups a product by the stores in its index document, which include any active store with an inventory row — paused, fee-suspended, out of stock or unavailable — so such a product stays in the local group, showing only the offers that are left. Favourites count only in-stock, available rows, so the same product can appear there under a courier store. Neither looks at a store's pause.
- **Up to two minutes of lag.** The locality cache and the suggest/browse caches each live 60 s, so a changed courier setting can take about two minutes to show in search.
- **Store-name search now reads the locality.** With a location, `GET /search/stores` uses the Redis-cached locality (a PostGIS pass per new 500 m cell); unlike suggest and products it has no rate limit of its own.
- **Per-row radii skip the spatial index.** Every store has its own radius, so the zone queries scan the active stores instead of using the GiST index. Fine at today's store count; revisit with thousands of stores.
- **Notification copy is English-only,** like every message in the repo. The UI is translated.
- **No returns.** If a parcel comes back, the seller restocks it by hand.
- **No follow-up once the seller holds the money.** `paid` and `packed` orders get no reminder and never count as stalled; only shipping past the delivery date does.
- **Abandoned orders hold stock.** A `pending`, `quoted` or unpaid `accepted` order nobody acts on keeps its reserved stock until someone cancels it; reminders never cancel.
- **₹0 acceptance still needs a payee.** Accepting requires a live UPI or bank-transfer payee even when store credit covers everything (allowed by the spec, but not strictly necessary).
- **Downgrade.** Rolling migration `4675f7be7055` back is only safe before the first courier order: any `courier`, `quoted` or `accepted` row makes older code fail to load that order.
- **Cost per list row.** Order lists run about four extra queries per courier order (quotes, payment, seller, courier row), and each reminder sweep (hourly outside quiet hours, so about 12 runs a day by default) takes one lock per active courier order and per cancelled order still owed a refund. Fine at current volumes; batch both if courier orders grow large.
