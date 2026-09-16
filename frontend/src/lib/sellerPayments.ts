// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { ApiError, patch } from "@/lib/api";
import type { SellerProfileChangeRequest } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Submit a UPI payee plus a verification QR image for admin review.
 *
 * The image is only so a reviewer can confirm it resolves to the same UPI ID —
 * it is never shown to customers, who always scan a QR generated from the VPA.
 */
export async function uploadUpiQr(
  upiVpa: string,
  file: Blob,
  token: string | null,
): Promise<SellerProfileChangeRequest> {
  const form = new FormData();
  form.append("upi_vpa", upiVpa);
  form.append("file", file, "upi-qr.webp");
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}/api/v1/sellers/me/payments/qr`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.detail ?? res.statusText, res.status);
  }
  return res.json() as Promise<SellerProfileChangeRequest>;
}

/**
 * Stop accepting UPI immediately — deliberately NOT a change request.
 *
 * A compromised UPI handle has to stop receiving money now, not after an admin
 * review. Disabling only ever removes a payment option, so it carries none of
 * the risk that makes *enabling* reviewable. The stored VPA is retained, so
 * re-enabling later needs no fresh review.
 */
export async function disableUpi(token: string): Promise<{ upi_enabled: boolean }> {
  return patch<{ upi_enabled: boolean }>(
    "/api/v1/sellers/me/payments/disable",
    {},
    token,
  );
}
