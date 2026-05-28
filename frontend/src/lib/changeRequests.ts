// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Seller profile change-request API client + UI metadata helpers.
 *
 * Wraps the seller-facing and admin-facing change-request endpoints with
 * typed fetch helpers, and provides shared UI constants (group labels,
 * status tones, open-status set) consumed by the profile cards, request
 * list/detail pages, and admin review screens.
 */

import { get, patch, post } from "@/lib/api";
import type {
  SellerProfileChangeGroup,
  SellerProfileChangeRequest,
  SellerProfileChangeStatus,
} from "@/types";

/** Human-readable label for each profile change group. */
export const GROUP_LABEL: Record<SellerProfileChangeGroup, string> = {
  identity: "Identity",
  address: "Business address",
  legal: "Legal documents",
  banking: "Banking",
  services: "Services",
  store_basics: "Delivery settings",
};

/** Maps a CR status to a UI tone bucket — used by badges/banners. */
export const STATUS_TONE: Record<
  SellerProfileChangeStatus,
  "info" | "warn" | "success" | "danger" | "muted"
> = {
  submitted: "info",
  changes_requested: "warn",
  approved: "success",
  rejected: "danger",
  withdrawn: "muted",
};

/** Statuses where the request is still actionable (seller or admin). */
export const OPEN_STATUSES: readonly SellerProfileChangeStatus[] = [
  "submitted",
  "changes_requested",
];

/** True when the request is still open (not in a terminal state). */
export function isOpen(cr: { status: SellerProfileChangeStatus }): boolean {
  return OPEN_STATUSES.includes(cr.status);
}

// --- Seller-facing API client ---

export async function listMyChangeRequests(
  token: string,
  status: "open" | "terminal" | "all" = "open",
): Promise<SellerProfileChangeRequest[]> {
  return get<SellerProfileChangeRequest[]>(
    `/api/v1/sellers/me/change-requests?status=${status}`,
    token,
  );
}

export async function getMyChangeRequest(
  token: string,
  crId: string,
): Promise<SellerProfileChangeRequest> {
  return get<SellerProfileChangeRequest>(
    `/api/v1/sellers/me/change-requests/${crId}`,
    token,
  );
}

export async function createMyChangeRequest(
  token: string,
  body: {
    group: SellerProfileChangeGroup;
    proposed: Record<string, unknown>;
    note?: string;
  },
): Promise<SellerProfileChangeRequest> {
  return post<SellerProfileChangeRequest>(
    "/api/v1/sellers/me/change-requests",
    body,
    token,
  );
}

export async function resubmitMyChangeRequest(
  token: string,
  crId: string,
  body: { proposed: Record<string, unknown>; note?: string },
): Promise<SellerProfileChangeRequest> {
  return patch<SellerProfileChangeRequest>(
    `/api/v1/sellers/me/change-requests/${crId}/resubmit`,
    body,
    token,
  );
}

export async function withdrawMyChangeRequest(
  token: string,
  crId: string,
): Promise<SellerProfileChangeRequest> {
  return post<SellerProfileChangeRequest>(
    `/api/v1/sellers/me/change-requests/${crId}/withdraw`,
    {},
    token,
  );
}

// --- Admin client ---

export async function adminListSellerCRs(
  token: string,
  sellerId: number,
  status: "open" | "terminal" | "all" = "open",
): Promise<SellerProfileChangeRequest[]> {
  return get<SellerProfileChangeRequest[]>(
    `/api/v1/admin/sellers/${sellerId}/change-requests?status=${status}`,
    token,
  );
}

export async function adminGetSellerCR(
  token: string,
  sellerId: number,
  crId: string,
): Promise<SellerProfileChangeRequest> {
  return get<SellerProfileChangeRequest>(
    `/api/v1/admin/sellers/${sellerId}/change-requests/${crId}`,
    token,
  );
}

export async function adminApproveCR(
  token: string,
  sellerId: number,
  crId: string,
  body: { applied?: Record<string, unknown>; note?: string },
): Promise<SellerProfileChangeRequest> {
  return post<SellerProfileChangeRequest>(
    `/api/v1/admin/sellers/${sellerId}/change-requests/${crId}/approve`,
    body,
    token,
  );
}

export async function adminRequestChangesCR(
  token: string,
  sellerId: number,
  crId: string,
  note: string,
): Promise<SellerProfileChangeRequest> {
  return post<SellerProfileChangeRequest>(
    `/api/v1/admin/sellers/${sellerId}/change-requests/${crId}/request-changes`,
    { note },
    token,
  );
}

export async function adminRejectCR(
  token: string,
  sellerId: number,
  crId: string,
  reason: string,
): Promise<SellerProfileChangeRequest> {
  return post<SellerProfileChangeRequest>(
    `/api/v1/admin/sellers/${sellerId}/change-requests/${crId}/reject`,
    { reason },
    token,
  );
}
