// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { ApiError, get, patch, post } from "@/lib/api";
import type {
  CustomerStats,
  DeliveryMode,
  Order,
  OrderListResponse,
  PaymentMethod,
  ReorderResolveResponse,
} from "@/types";

export async function listOrders(
  token: string,
  status?: "active" | "history"
): Promise<Order[]> {
  const path = status ? `/api/v1/orders?status=${status}` : "/api/v1/orders";
  const data = await get<OrderListResponse>(path, token);
  return data.orders;
}

export interface PagedOrdersParams {
  status?: string; // all | active | delivered | cancelled
  service_id?: string;
  q?: string;
  from_date?: string;
  to_date?: string;
  sort?: string; // date_desc | date_asc | total_desc | total_asc
  page: number;
  page_size: number;
  /** Courier stage filters (A1 Task 15). */
  delivery_mode?: DeliveryMode;
  needs?: "quote" | "payment_check" | "refund";
  stale?: boolean;
}

// Server-side filtered + paginated order listing against /api/v1/orders. The
// endpoint scopes results by the caller's role (customer → own, seller → own
// stores, admin → all), so this same helper backs the admin and seller pages.
export async function listOrdersPaged(
  token: string,
  params: PagedOrdersParams
): Promise<OrderListResponse> {
  const sp = new URLSearchParams();
  if (params.status && params.status !== "all") sp.set("status", params.status);
  if (params.service_id) sp.set("service_id", params.service_id);
  if (params.q && params.q.trim()) sp.set("q", params.q.trim());
  if (params.from_date) sp.set("from_date", params.from_date);
  if (params.to_date) sp.set("to_date", params.to_date);
  if (params.sort) sp.set("sort", params.sort);
  if (params.delivery_mode) sp.set("delivery_mode", params.delivery_mode);
  if (params.needs) sp.set("needs", params.needs);
  if (params.stale) sp.set("stale", "true");
  sp.set("page", String(params.page));
  sp.set("page_size", String(params.page_size));
  return get<OrderListResponse>(`/api/v1/orders?${sp.toString()}`, token);
}

export async function getOrder(token: string, orderId: number): Promise<Order> {
  return get<Order>(`/api/v1/orders/${orderId}`, token);
}

export async function reorder(
  token: string,
  orderId: number
): Promise<ReorderResolveResponse> {
  return post<ReorderResolveResponse>(`/api/v1/orders/${orderId}/reorder`, undefined, token);
}

export interface PlaceOrderArgs {
  customerAddressId: number | null;
  storeId: number;
  serviceId: number;
  paymentMethod: PaymentMethod;
  deliveryMode?: DeliveryMode;
  preferredDeliveryDate?: string | null;
  preferredDeliveryWindow?: string | null;
  /** Store credit auto-applies; pass false when the customer opts out. */
  applyStoreCredit?: boolean;
  /** Courier only: who the courier hands the parcel to (+91 mobile). */
  recipientName?: string | null;
  recipientPhone?: string | null;
}

export async function placeOrder(
  token: string,
  args: PlaceOrderArgs,
): Promise<Order> {
  const mode = args.deliveryMode ?? "door_delivery";
  return post<Order>(
    "/api/v1/orders",
    {
      customer_address_id: args.customerAddressId,
      store_id: args.storeId,
      service_id: args.serviceId,
      payment_method: args.paymentMethod,
      delivery_mode: mode,
      // A courier order has no preferred window; the server rejects one.
      preferred_delivery_date: mode === "courier" ? null : args.preferredDeliveryDate ?? null,
      preferred_delivery_window: mode === "courier" ? null : args.preferredDeliveryWindow ?? null,
      apply_store_credit: args.applyStoreCredit ?? true,
      // The server rejects recipient fields on non-courier orders.
      ...(mode === "courier"
        ? { recipient_name: args.recipientName ?? null, recipient_phone: args.recipientPhone ?? null }
        : {}),
    },
    token,
  );
}

export interface TrackingInput {
  carrier_name?: string;
  tracking_number?: string;
  tracking_url?: string;
}

export async function transitionOrder(
  token: string,
  orderId: number,
  to: "packed" | "dispatched" | "delivered",
  opts?: { otp?: string; reason?: string } & TrackingInput,
): Promise<Order> {
  return post<Order>(
    `/api/v1/orders/${orderId}/transition`,
    { to, ...(opts ?? {}) },
    token,
  );
}

export async function resendDeliveryOtp(
  token: string,
  orderId: number
): Promise<Order> {
  return post<Order>(
    `/api/v1/orders/${orderId}/delivery-otp/resend`,
    undefined,
    token,
  );
}

export async function cancelOrder(
  token: string,
  orderId: number,
  opts?: { reason?: string; paymentReceived?: boolean },
): Promise<Order> {
  return post<Order>(
    `/api/v1/orders/${orderId}/cancel`,
    {
      ...(opts?.reason ? { reason: opts.reason } : {}),
      ...(opts?.paymentReceived !== undefined ? { payment_received: opts.paymentReceived } : {}),
    },
    token,
  );
}


/** Record the customer's "I've paid" tap on a UPI order. Idempotent server-side:
 *  re-tapping does not move the recorded timestamp. */
export async function claimUpiPayment(
  token: string,
  orderId: number
): Promise<Order> {
  return post<Order>(`/api/v1/orders/${orderId}/payment/claim`, {}, token);
}

export interface CourierQuoteInput {
  courierFee: number;
  etaMinDays: number;
  etaMaxDays: number;
  carrierName?: string | null;
  note?: string | null;
}

export async function sendCourierQuote(
  token: string, orderId: number, q: CourierQuoteInput,
): Promise<Order> {
  return post<Order>(
    `/api/v1/orders/${orderId}/courier/quote`,
    {
      courier_fee: q.courierFee,
      eta_min_days: q.etaMinDays,
      eta_max_days: q.etaMaxDays,
      carrier_name: q.carrierName ?? null,
      note: q.note ?? null,
    },
    token,
  );
}

export async function acceptCourierQuote(
  token: string, orderId: number, quoteId: number,
): Promise<Order> {
  return post<Order>(`/api/v1/orders/${orderId}/courier/accept`, { quote_id: quoteId }, token);
}

/** The customer's "I've paid" on a courier order, naming the method used. */
export async function claimCourierPayment(
  token: string, orderId: number, method: "upi" | "net_banking",
): Promise<Order> {
  return post<Order>(`/api/v1/orders/${orderId}/payment/claim`, { method }, token);
}

export async function confirmCourierPayment(token: string, orderId: number): Promise<Order> {
  return post<Order>(`/api/v1/orders/${orderId}/payment/confirm`, undefined, token);
}

export async function rejectCourierPayment(
  token: string, orderId: number, note?: string,
): Promise<Order> {
  return post<Order>(
    `/api/v1/orders/${orderId}/payment/not-received`,
    note ? { note } : {},
    token,
  );
}

export async function updateCourierTracking(
  token: string, orderId: number, tracking: TrackingInput,
): Promise<Order> {
  return patch<Order>(`/api/v1/orders/${orderId}/courier/tracking`, tracking, token);
}

export async function markCourierReceived(token: string, orderId: number): Promise<Order> {
  return post<Order>(`/api/v1/orders/${orderId}/courier/received`, undefined, token);
}

export async function markRefundSent(
  token: string, orderId: number, reference?: string,
): Promise<Order> {
  return post<Order>(
    `/api/v1/orders/${orderId}/payment/refund-sent`,
    reference ? { reference } : {},
    token,
  );
}

export async function getCustomerStats(token: string): Promise<CustomerStats> {
  return get<CustomerStats>("/api/v1/customers/me/stats", token);
}

export async function submitOrderReview(
  token: string,
  orderId: number,
  rating: number,
  comment?: string | null,
): Promise<{ rating: number; comment: string | null }> {
  return post(
    `/api/v1/orders/${orderId}/review`,
    { rating, comment: comment ?? null },
    token,
  );
}

/** After a 403/409 on an order action the screen is usually stale: another
 *  tab, or the other party acted first. Re-read the order so the page catches
 *  up, keeping the error message on screen. Null when this read fails too. */
export async function refetchIfStale(
  token: string, orderId: number, err: unknown,
): Promise<Order | null> {
  if (!(err instanceof ApiError) || (err.status !== 409 && err.status !== 403)) return null;
  try {
    return await getOrder(token, orderId);
  } catch {
    return null;
  }
}
