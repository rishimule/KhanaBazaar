// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { get, post } from "@/lib/api";
import type {
  CustomerStats,
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
  customerAddressId: number;
  storeId: number;
  serviceId: number;
  paymentMethod: PaymentMethod;
}

export async function placeOrder(
  token: string,
  args: PlaceOrderArgs,
): Promise<Order> {
  return post<Order>(
    "/api/v1/orders",
    {
      customer_address_id: args.customerAddressId,
      store_id: args.storeId,
      service_id: args.serviceId,
      payment_method: args.paymentMethod,
    },
    token,
  );
}

export async function transitionOrder(
  token: string,
  orderId: number,
  to: "packed" | "dispatched" | "delivered",
  opts?: { otp?: string; reason?: string }
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

export async function cancelOrder(token: string, orderId: number): Promise<Order> {
  return post<Order>(`/api/v1/orders/${orderId}/cancel`, {}, token);
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
