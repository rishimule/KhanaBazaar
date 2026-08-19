// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Returns API client.
 *
 * Token-first argument order, matching `lib/orders.ts`. No try/catch here —
 * callers handle `ApiError` and read codes via `@/lib/errors`.
 */
import { get, patch, post } from "@/lib/api";
import type {
  ReturnEligibility,
  ReturnReasonCode,
  ReturnRequest,
  ReturnSettlementChoice,
  ReturnStatus,
  StoreCreditBalance,
  StoreCreditEntry,
} from "@/types";

export interface CreateReturnBody {
  order_id: number;
  order_item_ids: number[];
  reason_code: ReturnReasonCode;
  reason_note?: string | null;
  settlement_choice: ReturnSettlementChoice;
}

// ─── Customer ────────────────────────────────────────────────────────────

export async function getReturnEligibility(
  token: string,
  orderId: number
): Promise<ReturnEligibility> {
  return get<ReturnEligibility>(`/api/v1/returns/eligibility/${orderId}`, token);
}

export async function createReturn(
  token: string,
  body: CreateReturnBody
): Promise<ReturnRequest> {
  return post<ReturnRequest>("/api/v1/returns", body, token);
}

export async function confirmReturn(
  token: string,
  returnId: number,
  otp: string
): Promise<ReturnRequest> {
  return post<ReturnRequest>(
    `/api/v1/returns/${returnId}/confirm`,
    { otp, agreement_accepted: true },
    token
  );
}

export async function resendReturnOtp(
  token: string,
  returnId: number
): Promise<{ sent: boolean }> {
  return post<{ sent: boolean }>(
    `/api/v1/returns/${returnId}/otp/resend`,
    undefined,
    token
  );
}

export async function withdrawReturn(
  token: string,
  returnId: number
): Promise<ReturnRequest> {
  return post<ReturnRequest>(
    `/api/v1/returns/${returnId}/withdraw`,
    undefined,
    token
  );
}

export async function requestPaymentOtp(
  token: string,
  returnId: number
): Promise<{ sent: boolean }> {
  return post<{ sent: boolean }>(
    `/api/v1/returns/${returnId}/payment/otp/request`,
    undefined,
    token
  );
}

export async function confirmPaymentReceived(
  token: string,
  returnId: number,
  otp: string
): Promise<ReturnRequest> {
  return post<ReturnRequest>(
    `/api/v1/returns/${returnId}/payment/confirm`,
    { otp },
    token
  );
}

export async function listReturns(
  token: string,
  status?: ReturnStatus
): Promise<ReturnRequest[]> {
  const path = status
    ? `/api/v1/returns?status=${status}`
    : "/api/v1/returns";
  return get<ReturnRequest[]>(path, token);
}

export async function getReturn(
  token: string,
  returnId: number
): Promise<ReturnRequest> {
  return get<ReturnRequest>(`/api/v1/returns/${returnId}`, token);
}

export async function listStoreCredit(
  token: string
): Promise<StoreCreditBalance[]> {
  return get<StoreCreditBalance[]>("/api/v1/store-credit", token);
}

export async function getStoreCreditLedger(
  token: string,
  sellerProfileId: number
): Promise<StoreCreditEntry[]> {
  return get<StoreCreditEntry[]>(
    `/api/v1/store-credit/${sellerProfileId}/ledger`,
    token
  );
}

// ─── Seller ──────────────────────────────────────────────────────────────

export async function listSellerReturns(
  token: string,
  status?: ReturnStatus
): Promise<ReturnRequest[]> {
  const path = status
    ? `/api/v1/sellers/me/returns?status=${status}`
    : "/api/v1/sellers/me/returns";
  return get<ReturnRequest[]>(path, token);
}

export async function getSellerReturn(
  token: string,
  returnId: number
): Promise<ReturnRequest> {
  return get<ReturnRequest>(`/api/v1/sellers/me/returns/${returnId}`, token);
}

export async function acceptReturn(
  token: string,
  returnId: number,
  otp: string,
  restock: boolean
): Promise<ReturnRequest> {
  return post<ReturnRequest>(
    `/api/v1/sellers/me/returns/${returnId}/accept`,
    { otp, restock },
    token
  );
}

export async function rejectReturn(
  token: string,
  returnId: number,
  reason: string
): Promise<ReturnRequest> {
  return post<ReturnRequest>(
    `/api/v1/sellers/me/returns/${returnId}/reject`,
    { reason },
    token
  );
}

export async function setServiceReturnWindow(
  token: string,
  serviceId: number,
  days: number
): Promise<{ id: number; return_window_days: number }> {
  return patch<{ id: number; return_window_days: number }>(
    `/api/v1/sellers/me/services/${serviceId}/returns`,
    { return_window_days: days },
    token
  );
}

// ─── Admin ───────────────────────────────────────────────────────────────

export async function adminListReturns(
  token: string,
  params: { sellerId?: number; status?: ReturnStatus } = {}
): Promise<ReturnRequest[]> {
  const sp = new URLSearchParams();
  if (params.sellerId) sp.set("seller_id", String(params.sellerId));
  if (params.status) sp.set("status", params.status);
  const qs = sp.toString();
  return get<ReturnRequest[]>(
    `/api/v1/admin/returns${qs ? `?${qs}` : ""}`,
    token
  );
}

export async function adminGetReturn(
  token: string,
  returnId: number
): Promise<ReturnRequest> {
  return get<ReturnRequest>(`/api/v1/admin/returns/${returnId}`, token);
}

export async function adminForceAccept(
  token: string,
  returnId: number,
  reason: string,
  restock: boolean
): Promise<ReturnRequest> {
  return post<ReturnRequest>(
    `/api/v1/admin/returns/${returnId}/accept`,
    { reason, restock },
    token
  );
}

export async function adminForceReject(
  token: string,
  returnId: number,
  reason: string
): Promise<ReturnRequest> {
  return post<ReturnRequest>(
    `/api/v1/admin/returns/${returnId}/reject`,
    { reason },
    token
  );
}

export async function adminForceClose(
  token: string,
  returnId: number,
  reason: string
): Promise<ReturnRequest> {
  return post<ReturnRequest>(
    `/api/v1/admin/returns/${returnId}/close`,
    { reason },
    token
  );
}
