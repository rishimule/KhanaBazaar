// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Khana Bazaar — Account lifecycle self-service.
 *
 * Typed helpers for the customer-facing account soft-delete flow:
 *  - `deactivateAccount`  — reversible pause (customer can log back in).
 *  - `requestAccountDeleteOtp` — email a 6-digit confirmation code.
 *  - `deleteAccount` — terminal delete, gated by the emailed OTP.
 *
 * All three throw {@link ApiError} on failure; callers inspect `err.detail`
 * for the structured error payloads documented below:
 *  - 409 `{error:"open_obligations", open_orders, credit_accounts}` — the
 *    customer has non-terminal orders / outstanding credit and cannot leave.
 *  - 429 `{error:"rate_limited", retry_after}` — OTP request cooldown.
 *  - 422 `{error:"otp_invalid"}` — wrong or expired confirmation code.
 */

import { post } from "@/lib/api";

export interface DeactivateResponse {
  status: "deactivated";
}

export interface DeleteOtpRequestResponse {
  sent: boolean;
}

export interface DeleteResponse {
  status: "deleted";
}

/** Structured detail payloads the backend returns for the lifecycle endpoints. */
export interface OpenObligationsDetail {
  error: "open_obligations";
  open_orders: number;
  credit_accounts: number;
}

export interface RateLimitedDetail {
  error: "rate_limited";
  retry_after: number;
}

export interface OtpInvalidDetail {
  error: "otp_invalid";
}

/** Reversibly pause the customer's account. On success the session should be
 *  torn down (call `logout()`); the customer can reactivate by logging in. */
export function deactivateAccount(
  token: string,
  reason?: string | null,
): Promise<DeactivateResponse> {
  return post<DeactivateResponse>(
    "/api/v1/customers/me/deactivate",
    { reason: reason ?? null },
    token,
  );
}

/** Email a fresh 6-digit code used to confirm a permanent delete. Takes no body. */
export function requestAccountDeleteOtp(
  token: string,
): Promise<DeleteOtpRequestResponse> {
  return post<DeleteOtpRequestResponse>(
    "/api/v1/customers/me/delete/otp/request",
    undefined,
    token,
  );
}

/** Permanently delete the account, gated by the emailed OTP. Terminal — only an
 *  admin can restore afterwards. On success the session should be torn down. */
export function deleteAccount(
  token: string,
  code: string,
  reason?: string | null,
): Promise<DeleteResponse> {
  return post<DeleteResponse>(
    "/api/v1/customers/me/delete",
    { code, reason: reason ?? null },
    token,
  );
}
