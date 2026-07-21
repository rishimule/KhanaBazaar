// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Typed client for the admin customer-supervisor endpoints
 * (see backend/app/src/app/api/admin_customers.py).
 *
 * Every lifecycle write proxied through here records a transition + reason on
 * the backend. The UI collects reason strings (>= 10 chars) before invoking the
 * destructive helpers (suspend / unsuspend / delete / restore).
 */
import { get, post } from "./api";
import type {
  AdminCustomerActivity,
  AdminCustomerHub,
  AdminCustomerListResponse,
  AdminCustomerNotification,
  AdminCustomerOrder,
  CustomerAccountStatus,
  CustomerAddress,
  CustomerLifecycleAction,
} from "@/types";

export interface CustomerListParams {
  q?: string;
  status?: CustomerAccountStatus | "";
  limit: number;
  offset: number;
}

export function fetchCustomerList(token: string, params: CustomerListParams) {
  const sp = new URLSearchParams({
    limit: String(params.limit),
    offset: String(params.offset),
  });
  if (params.q && params.q.trim()) sp.set("q", params.q.trim());
  if (params.status) sp.set("status", params.status);
  return get<AdminCustomerListResponse>(
    `/api/v1/admin/customers?${sp.toString()}`,
    token,
  );
}

export function fetchCustomerHub(customerProfileId: number, token: string) {
  return get<AdminCustomerHub>(
    `/api/v1/admin/customers/${customerProfileId}`,
    token,
  );
}

export function fetchCustomerActivity(
  customerProfileId: number,
  token: string,
) {
  return get<AdminCustomerActivity[]>(
    `/api/v1/admin/customers/${customerProfileId}/activity`,
    token,
  );
}

export function fetchCustomerOrders(customerProfileId: number, token: string) {
  return get<AdminCustomerOrder[]>(
    `/api/v1/admin/customers/${customerProfileId}/orders`,
    token,
  );
}

export function fetchCustomerAddresses(
  customerProfileId: number,
  token: string,
) {
  return get<CustomerAddress[]>(
    `/api/v1/admin/customers/${customerProfileId}/addresses`,
    token,
  );
}

export function fetchCustomerNotifications(
  customerProfileId: number,
  token: string,
) {
  return get<AdminCustomerNotification[]>(
    `/api/v1/admin/customers/${customerProfileId}/notifications`,
    token,
  );
}

/** Apply a lifecycle transition. `reason` must be >= 10 chars (enforced UI-side
 * by AdminReasonModal and backend-side). Resolves to the new status. */
export function customerLifecycleAction(
  customerProfileId: number,
  action: CustomerLifecycleAction,
  reason: string,
  token: string,
) {
  return post<{ status: CustomerAccountStatus }>(
    `/api/v1/admin/customers/${customerProfileId}/${action}`,
    { reason },
    token,
  );
}
