// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Typed client for the admin supervisor endpoints
 * (see backend/app/src/app/api/admin_actions.py).
 *
 * Every write proxied through here triggers an `AdminActionLog` row on the
 * backend. The UI is responsible for collecting reason strings (>= 10 chars)
 * before invoking the destructive helpers.
 */
import { get, patch, post } from "./api";
import type {
  AdminActivityPage,
  AdminInventoryRow,
  Order,
  SellerHubSummary,
} from "@/types";

export function fetchSellerHub(sellerId: number, token: string) {
  return get<SellerHubSummary>(`/api/v1/admin/sellers/${sellerId}`, token);
}

export function fetchSellerActivity(
  sellerId: number,
  token: string,
  cursor?: string | null,
) {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return get<AdminActivityPage>(
    `/api/v1/admin/sellers/${sellerId}/activity${qs}`,
    token,
  );
}

export function fetchSellerInventory(sellerId: number, token: string) {
  return get<AdminInventoryRow[]>(
    `/api/v1/admin/sellers/${sellerId}/inventory`,
    token,
  );
}

export function fetchSellerOrders(sellerId: number, token: string) {
  return get<{ orders: Order[] }>(
    `/api/v1/orders?seller_id=${sellerId}`,
    token,
  );
}

export function adminRewindOrder(
  orderId: number,
  body: { to_status: "pending" | "packed"; reason: string },
  token: string,
) {
  return post<{ status: string }>(
    `/api/v1/admin/orders/${orderId}/rewind`,
    body,
    token,
  );
}

export function adminRefundOrder(
  orderId: number,
  body: { reason: string },
  token: string,
) {
  return post<{ status: string }>(
    `/api/v1/admin/orders/${orderId}/refund`,
    body,
    token,
  );
}

export function adminOverrideDeliveryAddress(
  orderId: number,
  body: { address: unknown; reason: string },
  token: string,
) {
  return patch<{ status: string }>(
    `/api/v1/admin/orders/${orderId}/delivery-address`,
    body,
    token,
  );
}
