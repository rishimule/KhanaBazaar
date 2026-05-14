// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { get, post } from "@/lib/api";
import type { CustomerStats, Order, OrderListResponse, PaymentMethod } from "@/types";

export async function listOrders(
  token: string,
  status?: "active" | "history"
): Promise<Order[]> {
  const path = status ? `/api/v1/orders?status=${status}` : "/api/v1/orders";
  const data = await get<OrderListResponse>(path, token);
  return data.orders;
}

export async function getOrder(token: string, orderId: number): Promise<Order> {
  return get<Order>(`/api/v1/orders/${orderId}`, token);
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
  to: "packed" | "dispatched" | "delivered"
): Promise<Order> {
  return post<Order>(`/api/v1/orders/${orderId}/transition`, { to }, token);
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
