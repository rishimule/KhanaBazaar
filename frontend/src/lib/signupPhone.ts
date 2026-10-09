// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Pre-account phone step of customer signup (spec 2026-10-08).
 *
 * `request` needs the email plus its still-live login code. With phone OTP
 * off it answers `otp_required: false` and the `phone_token` at once;
 * otherwise a code goes to the phone and `verify` trades it for the token.
 * Account creation (`/auth/otp/verify` for a new email, `/referrals/accept`)
 * requires that token. The response — never public-config — decides whether
 * a code step is shown.
 */
import { ApiError, post } from "@/lib/api";

export interface SignupPhoneRequestResult {
  otp_required: boolean;
  phone_token?: string;
  expires_in?: number;
}

/** The token minted for one email + number, kept so a retry after an
 * unrelated error neither re-asks for nor re-texts that number. */
export type SignupPhoneCache = { email: string; phone: string; token: string } | null;

export function requestSignupPhoneOtp(input: {
  email: string;
  email_code: string;
  phone: string;
}): Promise<SignupPhoneRequestResult> {
  return post<SignupPhoneRequestResult>(
    "/api/v1/auth/customer/phone/otp/request",
    input,
  );
}

export function verifySignupPhoneOtp(input: {
  email: string;
  phone: string;
  code: string;
}): Promise<{ phone_token: string }> {
  return post<{ phone_token: string }>(
    "/api/v1/auth/customer/phone/otp/verify",
    input,
  );
}

/** A cooldown 429 from `request` that says the code is already on its way:
 * our first request reached the server but its response never reached us
 * (spec §4.2). The caller can go straight to the code step. */
export function codeAlreadySent(err: unknown): boolean {
  if (!(err instanceof ApiError)) return false;
  const d = err.detail;
  return Boolean(
    d && typeof d === "object" && (d as { code_sent?: unknown }).code_sent === true,
  );
}

/** `retry_after` (seconds) from a 429 body, when the server sent one. */
export function retryAfterSeconds(err: unknown): number | null {
  if (!(err instanceof ApiError)) return null;
  const d = err.detail;
  if (d && typeof d === "object" && "retry_after" in d) {
    const n = Number((d as { retry_after: unknown }).retry_after);
    return Number.isFinite(n) && n > 0 ? Math.ceil(n) : null;
  }
  return null;
}
