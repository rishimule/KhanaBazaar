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
import { post } from "@/lib/api";

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
