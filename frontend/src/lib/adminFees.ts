// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Admin platform-fee API client + types. Mirrors api/platform_fees.py admin_router
 * (/api/v1/admin/fees/*). Admin-only; operator English copy. Errors come back as
 * `detail = {"error": "<code>"}` (see feeErrorCode).
 */
import { get, patch, put, post, ApiError } from "./api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type PlatformFeeSettings = {
  grace_period_days: number;
  expiry_reminder_start_days: number;
  pending_payment_protect_days: number;
  bank_account_name: string | null;
  bank_account_number: string | null;
  bank_ifsc: string | null;
  upi_id: string | null;
  qr_image_url: string | null;
  gstin: string | null;
};

export type PlatformFeeSettingsPatch = Partial<PlatformFeeSettings>;

export type SubscriptionPlanItem = {
  duration_months: number;
  price: number;
  is_active: boolean;
};

export type ServiceFeeConfig = {
  service_id: number;
  freebie_enabled: boolean;
  freebie_default_days: number;
  subscription_enabled: boolean;
  order_value_enabled: boolean;
  order_value_percent: number;
  order_value_min_deposit: number;
  order_value_billing_day: number;
  order_value_payment_days: number;
  pay_per_txn_enabled: boolean;
  pay_per_txn_fee: number;
  pay_per_txn_min_deposit: number;
  pay_per_txn_low_balance_threshold: number;
};

export type ServiceFeeConfigWithPlans = {
  config: ServiceFeeConfig;
  plans: SubscriptionPlanItem[];
};

// Confirmation queue (4e)
export type PaymentQueueItem = {
  payment_id: number;
  arrangement_id: number;
  store_id: number;
  store_name: string;
  service_id: number;
  service_name: string;
  kind: string;
  amount: number;
  seller_note: string | null;
  pending_since: string | null;
  created_at: string;
};

// Per-seller arrangements (4f)
export type ArrangementSummary = {
  id: number;
  service_id: number;
  service_name: string;
  model: string;
  status: string;
  valid_until: string | null;
  cancel_requested: boolean;
  pending: boolean;
};

// Store wallet credit worklist
export type StoreCreditView = {
  store_id: number;
  store_name: string;
  fee_credit_balance: number;
};

// Order Value % monthly invoice (mirrors backend InvoiceView).
export type FeeInvoice = {
  id: number;
  arrangement_id: number;
  service_id: number;
  period_start: string;
  period_end: string;
  sales_total: number;
  fee_percent_snapshot: number;
  amount_due: number;
  status: string;
  issued_on: string;
  due_date: string;
  suspend_after: string;
  paid_at: string | null;
  payment_pending: boolean;
};

export function feeErrorCode(err: unknown): string | null {
  if (err instanceof ApiError) {
    const d = err.detail as unknown;
    if (d && typeof d === "object" && "error" in d) return String((d as { error: unknown }).error);
    if (typeof d === "string") return d;
  }
  return null;
}

// ── 4d: global settings + per-service config ────────────────────────────────
export function getFeeSettings(token: string | null): Promise<PlatformFeeSettings> {
  return get<PlatformFeeSettings>("/api/v1/admin/fees/settings", token);
}

export function patchFeeSettings(
  token: string | null,
  body: PlatformFeeSettingsPatch,
): Promise<PlatformFeeSettings> {
  return patch<PlatformFeeSettings>("/api/v1/admin/fees/settings", body, token);
}

// Multipart upload — the shared api.ts helpers force application/json, so use a
// raw fetch (mirrors lib/avatars.ts). Returns the updated settings.
export async function uploadFeeQr(
  token: string | null,
  file: File,
): Promise<PlatformFeeSettings> {
  const form = new FormData();
  form.append("file", file, file.name);
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}/api/v1/admin/fees/settings/qr`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.detail ?? res.statusText, res.status);
  }
  return res.json() as Promise<PlatformFeeSettings>;
}

export function getServiceFeeConfig(
  token: string | null,
  serviceId: number,
): Promise<ServiceFeeConfigWithPlans> {
  return get<ServiceFeeConfigWithPlans>(`/api/v1/admin/fees/services/${serviceId}`, token);
}

export function patchServiceFeeConfig(
  token: string | null,
  serviceId: number,
  body: Partial<Omit<ServiceFeeConfig, "service_id">>,
): Promise<ServiceFeeConfig> {
  return patch<ServiceFeeConfig>(`/api/v1/admin/fees/services/${serviceId}`, body, token);
}

export function putServicePlans(
  token: string | null,
  serviceId: number,
  plans: SubscriptionPlanItem[],
): Promise<SubscriptionPlanItem[]> {
  return put<SubscriptionPlanItem[]>(
    `/api/v1/admin/fees/services/${serviceId}/plans`,
    { plans },
    token,
  );
}

// ── 4e: confirmation queue ──────────────────────────────────────────────────
export function getFeeQueue(token: string | null): Promise<PaymentQueueItem[]> {
  return get<PaymentQueueItem[]>("/api/v1/admin/fees/queue", token);
}

export function confirmFeePayment(
  token: string | null,
  paymentId: number,
): Promise<{ arrangement_id: number; status: string; valid_until: string | null }> {
  return post(`/api/v1/admin/fees/payments/${paymentId}/confirm`, undefined, token);
}

export function rejectFeePayment(
  token: string | null,
  paymentId: number,
  reason: string,
): Promise<{ payment_id: number; status: string }> {
  return post(`/api/v1/admin/fees/payments/${paymentId}/reject`, { reason }, token);
}

// ── 4f: per-seller arrangement overrides ────────────────────────────────────
export function getStoreArrangements(
  token: string | null,
  storeId: number,
): Promise<ArrangementSummary[]> {
  return get<ArrangementSummary[]>(`/api/v1/admin/fees/arrangements/${storeId}`, token);
}

export function extendArrangement(
  token: string | null,
  arrangementId: number,
  days: number,
  reason?: string,
): Promise<{ arrangement_id: number; valid_until: string | null }> {
  return post(
    `/api/v1/admin/fees/arrangements/${arrangementId}/extend`,
    { days, reason },
    token,
  );
}

export function terminateArrangement(
  token: string | null,
  arrangementId: number,
  reason: string,
): Promise<{ arrangement_id: number; status: string }> {
  return post(
    `/api/v1/admin/fees/arrangements/${arrangementId}/terminate`,
    { reason },
    token,
  );
}

export function compArrangement(
  token: string | null,
  arrangementId: number,
  durationMonths: number,
  reason?: string,
): Promise<{ arrangement_id: number; status: string; valid_until: string | null }> {
  return post(
    `/api/v1/admin/fees/arrangements/${arrangementId}/comp`,
    { duration_months: durationMonths, reason },
    token,
  );
}

// Force-switch a store's plan at any balance (disposition settles leftover PPT
// balance: "credit" | "cash_out" | "waive").
export function switchArrangement(
  token: string | null,
  arrangementId: number,
  targetModel: string,
  reason: string,
  opts?: { durationMonths?: number; disposition?: string },
): Promise<{ arrangement_id: number; status: string; model: string }> {
  return post(
    `/api/v1/admin/fees/arrangements/${arrangementId}/switch`,
    {
      target_model: targetModel,
      duration_months: opts?.durationMonths,
      disposition: opts?.disposition ?? "credit",
      reason,
    },
    token,
  );
}

// ── Order Value % (postpaid) — invoices + deposit settlement ────────────────
export function getArrangementInvoices(
  token: string | null,
  arrangementId: number,
): Promise<FeeInvoice[]> {
  return get<FeeInvoice[]>(
    `/api/v1/admin/fees/arrangements/${arrangementId}/invoices`,
    token,
  );
}

export function forfeitDeposit(
  token: string | null,
  arrangementId: number,
  amount: number,
  reason: string,
  invoiceId?: number,
): Promise<{
  arrangement_id: number;
  status: string;
  security_deposit_amount: number;
  balance: number;
}> {
  return post(
    `/api/v1/admin/fees/arrangements/${arrangementId}/forfeit`,
    { amount, reason, invoice_id: invoiceId },
    token,
  );
}

export function refundDeposit(
  token: string | null,
  arrangementId: number,
  mode: "offline" | "credit",
  note?: string,
): Promise<{ arrangement_id: number; refunded: number; mode: string }> {
  return post(
    `/api/v1/admin/fees/arrangements/${arrangementId}/refund-deposit`,
    { mode, note },
    token,
  );
}

// Apply a store's wallet credit to a PPT arrangement on the seller's behalf.
export function applyCreditOnBehalf(
  token: string | null,
  arrangementId: number,
  amount: number,
  reason: string,
): Promise<{ arrangement_id: number; applied: number; balance: number; status: string }> {
  return post(
    `/api/v1/admin/fees/arrangements/${arrangementId}/apply-credit`,
    { amount, reason },
    token,
  );
}

// ── Wallet credit worklist ──────────────────────────────────────────────────
export function listStoreCredit(token: string | null): Promise<StoreCreditView[]> {
  return get<StoreCreditView[]>("/api/v1/admin/fees/stores/credit", token);
}

export function grantStoreCredit(
  token: string | null,
  storeId: number,
  amount: number,
  reason: string,
): Promise<{ store_id: number; fee_credit_balance: number }> {
  return post(`/api/v1/admin/fees/stores/${storeId}/credit/grant`, { amount, reason }, token);
}

export function adjustStoreCredit(
  token: string | null,
  storeId: number,
  amount: number,
  reason: string,
): Promise<{ store_id: number; fee_credit_balance: number }> {
  return post(`/api/v1/admin/fees/stores/${storeId}/credit/adjust`, { amount, reason }, token);
}

export function cashOutStoreCredit(
  token: string | null,
  storeId: number,
  amount: number,
  reason: string,
): Promise<{ store_id: number; fee_credit_balance: number }> {
  return post(`/api/v1/admin/fees/stores/${storeId}/credit/cash-out`, { amount, reason }, token);
}
