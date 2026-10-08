// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { ApiError, get, patch } from "@/lib/api";
import type {
  PaymentMethodSwitches,
  PaymentSettings,
  SellerProfileChangeRequest,
} from "@/types";

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

/** Mirrors the backend `_UPI_VPA_RE`: the bank handle must start with a letter. */
export const UPI_VPA_REGEX = /^[A-Za-z0-9._-]{2,64}@[A-Za-z][A-Za-z0-9.-]{1,64}$/;

export function getPaymentSettings(token: string): Promise<PaymentSettings> {
  return get<PaymentSettings>("/api/v1/sellers/me/payments", token);
}

/** Flip switches — instant, no review. Returns the full settings so the page
 *  re-syncs with anything another tab or an admin changed. */
export function setPaymentMethods(
  token: string,
  changes: PaymentMethodSwitches,
): Promise<PaymentSettings> {
  return patch<PaymentSettings>("/api/v1/sellers/me/payments/methods", changes, token);
}

/** The delivery mode a `last_payment_method` refusal names, or null when
 *  `err` is something else. */
export function lastMethodMode(err: unknown): "door_delivery" | "pickup" | null {
  if (!(err instanceof ApiError)) return null;
  const detail = err.detail as { code?: unknown; mode?: unknown } | null;
  if (!detail || typeof detail !== "object" || detail.code !== "last_payment_method") {
    return null;
  }
  return detail.mode === "pickup" ? "pickup" : "door_delivery";
}

export function maskAccountNumber(n: string | null | undefined): string | null {
  if (!n) return null;
  const last4 = n.slice(-4);
  if (last4.length < 4) return null;
  return `•••• •••• ${last4}`;
}
