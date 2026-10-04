// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Pure courier helpers (spec 2026-10-02). No React, no fetches — every screen
 * that branches on courier state reads it through these, so the rules live in
 * one place.
 */
import type { ServiceabilityResult } from "@/lib/geo";
import type {
  Address,
  CourierQuote,
  DeliveryMode,
  Order,
  OrderStatus,
  PaymentMethod,
} from "@/types";

/** Why a saved address can or cannot take this sub-basket at checkout.
 *  `no_pin` = the saved address has no map coordinates, so no zone exists.
 *  `check_failed` = the serviceability call failed (network, 429) — never
 *  shown as "outside the area", which would be a confident wrong answer. */
export type AddressCourierZone =
  | "local"
  | "courier"
  | "none"
  | "no_pin"
  | "check_failed"
  | "service_no_courier"
  | "destination_unsupported";

export const COURIER_PREPAID_METHODS: PaymentMethod[] = ["upi", "net_banking"];

const INDIA_PIN = /^[1-9]\d{5}$/;

/** Couriers deliver to Indian addresses with a 6-digit PIN (mirrors the
 *  server's checkout rule, so the picker explains before the 422). */
export function isCourierDestination(address: Pick<Address, "country" | "pincode">): boolean {
  return address.country === "India" && INDIA_PIN.test(address.pincode ?? "");
}

/** Classify one saved address for a (store, service) from a store-scoped
 *  serviceability result (called WITHOUT service_id, so `courier_service_ids`
 *  says which services ship). */
export function classifyAddressZone(
  result: ServiceabilityResult,
  serviceId: number,
  address: Pick<Address, "country" | "pincode">,
): AddressCourierZone {
  if (result.zone === "local") return "local";
  if (result.zone !== "courier") return "none";
  if (!(result.courier_service_ids ?? []).includes(serviceId)) return "service_no_courier";
  if (!isCourierDestination(address)) return "destination_unsupported";
  return "courier";
}

export function isOrderableZone(zone: AddressCourierZone | null | undefined): boolean {
  return zone === "local" || zone === "courier";
}

/** The Intl tag for an app locale: English reads Indian-style ("4 Oct",
 *  "3 Oct 2026, 3:49 pm"), and every language keeps Latin digits so dates
 *  match the amounts beside them (Marathi would otherwise use Devanagari). */
function intlLocale(locale: string): string {
  return `${locale === "en" ? "en-IN" : locale}-u-nu-latn`;
}

/** "4 Oct" in the viewer's locale. Accepts YYYY-MM-DD or a Date. */
export function formatShortDate(value: string | Date, locale: string): string {
  const d = typeof value === "string" ? new Date(`${value}T00:00:00`) : value;
  return d.toLocaleDateString(intlLocale(locale), { day: "numeric", month: "short" });
}

/** A timestamp in the page's language and the viewer's own (browser) time
 *  zone. Not next-intl's formatter: it inherits the server's zone, which is
 *  UTC on Cloud Run, so Indian customers would see times 5½ hours off. */
export function formatDateTime(value: string | Date, locale: string): string {
  const d = typeof value === "string" ? new Date(value) : value;
  return d.toLocaleString(intlLocale(locale), { dateStyle: "medium", timeStyle: "short" });
}

/** Today's calendar day in IST as a local-midnight Date (display only). */
function istToday(now: Date): Date {
  const ist = new Date(now.getTime() + 5.5 * 60 * 60 * 1000);
  return new Date(ist.getUTCFullYear(), ist.getUTCMonth(), ist.getUTCDate());
}

function addDays(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}

/** Arrival window if the customer paid today — the quote's days counted from
 *  today in IST, exactly how the server fixes the dates on confirmation. */
export function previewEtaWindow(
  quote: Pick<CourierQuote, "eta_min_days" | "eta_max_days">,
  now: Date = new Date(),
): { from: Date; to: Date } {
  const today = istToday(now);
  return { from: addDays(today, quote.eta_min_days), to: addDays(today, quote.eta_max_days) };
}

export function latestQuote(order: Order): CourierQuote | null {
  return order.courier?.quotes[0] ?? null;
}

/** The fields the courier status predicates read; list rows that carry less
 *  than a full Order (admin customer orders) satisfy it too. */
export type CourierStatusFields = { status: OrderStatus; delivery_mode?: DeliveryMode };

/** Before acceptance the courier charge is not in `order.total`. */
export function courierChargePending(order: CourierStatusFields): boolean {
  return (
    order.delivery_mode === "courier" &&
    (order.status === "pending" || order.status === "quoted")
  );
}

/** True when the customer — not the seller — must act next. */
export function customerActionNeeded(order: Order): boolean {
  if (order.delivery_mode !== "courier") return false;
  if (order.status === "quoted") return true;
  return order.status === "accepted" && !order.payment.customer_claimed_at;
}

/** The link's domain, shown next to a tracking link so a customer can see
 *  where it goes before tapping it. */
export function trackingHost(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname;
  } catch {
    return null;
  }
}

/** Straight-line km between the store and the delivery pin — a rough guide
 *  for booking the courier (spec §14 "distance"), not a road distance. */
export function straightLineKm(
  order: Pick<Order, "store_latitude" | "store_longitude" | "delivery_latitude" | "delivery_longitude">,
): number | null {
  const {
    store_latitude: lat1,
    store_longitude: lng1,
    delivery_latitude: lat2,
    delivery_longitude: lng2,
  } = order;
  if (lat1 == null || lng1 == null || lat2 == null || lng2 == null) return null;
  const rad = (d: number) => (d * Math.PI) / 180;
  const h =
    Math.sin(rad(lat2 - lat1) / 2) ** 2 +
    Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(rad(lng2 - lng1) / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
}
