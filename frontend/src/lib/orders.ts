import { get, post } from "@/lib/api";
import type { Order, OrderListResponse, PlaceOrderResponse } from "@/types";

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

export async function placeOrder(
  token: string,
  customerAddressId: number
): Promise<Order[]> {
  const data = await post<PlaceOrderResponse>(
    "/api/v1/orders",
    { customer_address_id: customerAddressId },
    token
  );
  return data.orders;
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
