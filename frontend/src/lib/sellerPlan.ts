// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Seller plan (platform-fee) API client + types. Mirrors the backend
 * SellerPlanView contract (api/platform_fees.py seller_router). Operator-only,
 * English copy. Errors come back as `detail = {"error": "<code>"}`.
 */
import { get, post, ApiError } from "./api";

export type SubscriptionPlanItem = {
  duration_months: number;
  price: number;
  is_active: boolean;
};

export type SellerPlanServiceView = {
  service_id: number;
  /** "freebie" | "subscription" | "order_value_percent" | "pay_per_transaction" */
  model: string;
  /** "trial" | "pending_activation" | "active" | "grace" | "suspended" */
  status: string;
  service_name: string;
  valid_until: string | null;
  subscription_enabled: boolean;
  subscription_plans: SubscriptionPlanItem[];
  payment_pending: boolean;
  amount_due: number | null;
  cancel_requested: boolean;
  // Pay-Per-Transaction (prepaid) fields.
  pay_per_txn_enabled: boolean;
  pay_per_txn_fee: number;
  pay_per_txn_min_deposit: number;
  /** Prepaid balance — present only when the arrangement is Pay-Per-Transaction. */
  balance: number | null;
  low_balance_threshold: number | null;
};

export type SellerPaymentDetails = {
  bank_account_name: string | null;
  bank_account_number: string | null;
  bank_ifsc: string | null;
  upi_id: string | null;
  qr_image_url: string | null;
  gstin: string | null;
};

export type SellerPlanView = {
  services: SellerPlanServiceView[];
  payment_details: SellerPaymentDetails;
  /** Store-level wallet credit (auto-applied to future fee obligations). */
  fee_credit_balance: number;
};

/**
 * FastAPI raises `HTTPException(detail={"error": "code"})`; `api.ts` stores
 * that verbatim on `ApiError.detail`. Extract the machine code regardless of
 * whether detail is the object form or a bare string.
 */
export function feeErrorCode(err: unknown): string | null {
  if (err instanceof ApiError) {
    const d = err.detail as unknown;
    if (d && typeof d === "object" && "error" in d) {
      return String((d as { error: unknown }).error);
    }
    if (typeof d === "string") return d;
  }
  return null;
}

export function getMyPlan(token: string | null): Promise<SellerPlanView> {
  return get<SellerPlanView>("/api/v1/sellers/me/plan", token);
}

export function optIn(
  serviceId: number,
  durationMonths: number,
  token: string | null,
): Promise<{ payment_id: number; amount: number }> {
  return post(
    `/api/v1/sellers/me/plan/${serviceId}/opt-in`,
    { duration_months: durationMonths },
    token,
  );
}

export function markPaid(
  serviceId: number,
  sellerNote: string | null,
  token: string | null,
): Promise<{ payment_id: number }> {
  return post(
    `/api/v1/sellers/me/plan/${serviceId}/mark-paid`,
    { seller_note: sellerNote },
    token,
  );
}

export function cancelPlan(
  serviceId: number,
  token: string | null,
): Promise<{ service_id: number; cancel_requested: boolean }> {
  return post(`/api/v1/sellers/me/plan/${serviceId}/cancel`, undefined, token);
}

// ── Pay-Per-Transaction (prepaid) ────────────────────────────────────────

export function optInPpt(
  serviceId: number,
  depositAmount: number,
  useCredit: boolean,
  token: string | null,
): Promise<{ payment_id: number | null; amount?: number; status?: string }> {
  return post(
    `/api/v1/sellers/me/plan/${serviceId}/pay-per-transaction/opt-in`,
    { deposit_amount: depositAmount, use_credit: useCredit },
    token,
  );
}

export function topUpPpt(
  serviceId: number,
  amount: number,
  token: string | null,
): Promise<{ payment_id: number; amount: number }> {
  return post(
    `/api/v1/sellers/me/plan/${serviceId}/top-up`,
    { amount },
    token,
  );
}

export function applyCreditPpt(
  serviceId: number,
  amount: number,
  token: string | null,
): Promise<{ applied: number; balance: number; status: string }> {
  return post(
    `/api/v1/sellers/me/plan/${serviceId}/apply-credit`,
    { amount },
    token,
  );
}

export function switchFromPpt(
  serviceId: number,
  token: string | null,
): Promise<{ service_id: number; status: string }> {
  return post(`/api/v1/sellers/me/plan/${serviceId}/switch`, undefined, token);
}
