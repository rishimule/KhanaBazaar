// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Client helpers for the authenticated seller phone-change OTP flow.
 *
 * A logged-in seller proves control of a NEW phone number before an identity
 * change request that changes the phone can be submitted. `verify` returns a
 * short-lived `phone_change_token` that the change-request create/resubmit
 * calls must carry.
 */
import { ApiError, post } from "@/lib/api";

/**
 * Mirror the backend `core.otp.normalize_phone` canonical form so the FE's
 * "phone changed" / "phone verified" comparisons key off the same string the
 * server binds the token to. Returns the canonical `+91XXXXXXXXXX` when valid,
 * otherwise the whitespace/hyphen-stripped input (so comparisons stay stable
 * while the user is still typing).
 */
export function normalizeIndianPhone(raw: string): string {
  const cleaned = raw.replace(/[\s-]/g, "");
  return /^\+91[6-9]\d{9}$/.test(cleaned) ? cleaned : cleaned;
}

/** Map a phone-OTP API error to user-facing copy. The OTP endpoints return
 * `detail` as an object (`{error, retry_after?}`), which ApiError.message
 * flattens to "HTTP NNN" — unwrap it here. */
export function phoneOtpErrorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    const d: unknown = e.detail;
    const code =
      typeof d === "object" && d !== null && "error" in d
        ? String((d as { error: unknown }).error)
        : typeof d === "string"
          ? d
          : "";
    switch (code) {
      case "phone_taken":
        return "That number is already used by another seller.";
      case "phone_unchanged":
        return "This is already your current number.";
      case "invalid_phone":
        return "Enter a valid Indian mobile number.";
      case "invalid_code":
        return "Incorrect code. Please try again.";
      case "code_expired_or_used":
        return "That code expired. Request a new one.";
      case "too_many_attempts":
        return "Too many attempts. Request a new code.";
      case "rate_limited": {
        const ra =
          typeof d === "object" && d !== null && "retry_after" in d
            ? Number((d as { retry_after: unknown }).retry_after)
            : 0;
        return ra > 0
          ? `Please wait ${ra}s before requesting another code.`
          : "Please wait before requesting another code.";
      }
      default:
        return e.message;
    }
  }
  return e instanceof Error ? e.message : "Something went wrong";
}

export async function requestSellerPhoneOtp(
  token: string,
  phone: string,
): Promise<void> {
  await post("/api/v1/sellers/me/phone/otp/request", { phone }, token);
}

export async function verifySellerPhoneOtp(
  token: string,
  phone: string,
  code: string,
): Promise<string> {
  const res = await post<{ phone_change_token: string }>(
    "/api/v1/sellers/me/phone/otp/verify",
    { phone, code },
    token,
  );
  return res.phone_change_token;
}
