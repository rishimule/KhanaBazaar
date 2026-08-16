// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Khana Bazaar — Error → translation key mapping.
 *
 * Maps an error from the API client to a key in the `Errors` namespace
 * (see frontend/messages/*.json). Call sites are expected to:
 *   1. Call `apiErrorKey(err)`.
 *   2. If it returns a key, render `t(key)` with the `Errors` namespace.
 *   3. If it returns `null`, fall back to the raw `err.detail` string
 *      (or any locally appropriate default).
 *
 * This helper is opt-in: existing call sites are unchanged. Adopt
 * incrementally where the UX benefits from a localized error message.
 *
 * Usage example:
 *
 *   const t = useTranslations("Errors");
 *   try {
 *     await post(...);
 *   } catch (err) {
 *     const key = apiErrorKey(err);
 *     setError(key ? t(key.replace(/^Errors\./, "")) : (err as ApiError).detail);
 *   }
 */

import { ApiError } from "./api";

/**
 * Read the machine-readable code out of a caught API error, whatever shape the
 * backend used.
 *
 * FastAPI handlers in this repo raise four different shapes for one idea:
 *   detail: "forbidden"                          — bare string
 *   detail: { code: "terminal_status" }          — most of services/orders.py
 *   detail: { detail: "illegal_transition", … }  — services/orders.py:104, :386
 *   detail: { error: "review_exists" }           — api/orders.py:714, :720
 *
 * Always returns a string or null — never an object — because callers push the
 * result into render state.
 */
export function apiErrorCode(err: unknown): string | null {
  if (!(err instanceof ApiError)) return null;
  const detail = err.detail;
  if (typeof detail === "string") return detail || null;
  if (detail && typeof detail === "object") {
    const bag = detail as Record<string, unknown>;
    for (const key of ["code", "detail", "error"]) {
      const value = bag[key];
      if (typeof value === "string" && value) return value;
    }
  }
  return null;
}

export function apiErrorKey(err: unknown): string | null {
  if (!(err instanceof ApiError)) {
    if (err instanceof TypeError) return "Errors.network";
    return null;
  }

  const detail = apiErrorCode(err) ?? "";
  const lower = detail.toLowerCase();

  // Detail-string matches that should win over the generic status fallback.
  if (lower === "service_unavailable") return "Errors.service_unavailable";
  if (lower === "service_mismatch") return "Errors.service_mismatch";
  if (lower === "store_paused" || lower === "service_paused")
    return "Errors.store_paused";

  // Order-lifecycle codes. These arrive object-shaped, so they were unreachable
  // before apiErrorCode() normalised the three key names the backend uses.
  if (lower === "illegal_transition") return "Errors.illegal_transition";
  if (lower === "terminal_status") return "Errors.terminal_status";
  if (lower === "seller_not_active") return "Errors.seller_not_active";
  if (lower === "order_not_mutable") return "Errors.order_not_mutable";
  if (lower === "not_dispatched") return "Errors.not_dispatched";

  switch (err.status) {
    case 401:
      return "Errors.unauthorized";
    case 403:
      return "Errors.forbidden";
    case 404:
      return "Errors.notFound";
    case 409:
      return "Errors.conflict";
    case 422:
      return "Errors.validation";
    case 429:
      if (lower.includes("otp")) return "Errors.otpRateLimit";
      return "Errors.unknown";
    case 400:
      if (lower.includes("otp") && lower.includes("expired")) {
        return "Errors.otpExpired";
      }
      if (
        lower.includes("otp") &&
        (lower.includes("invalid") || lower.includes("incorrect"))
      ) {
        return "Errors.otpInvalid";
      }
      return null;
    default:
      if (err.status >= 500) return "Errors.serverError";
      return null;
  }
}

/** `apiErrorKey` with the `Errors.` prefix stripped, ready to hand straight to
 * `useTranslations("Errors")`. Returns null when nothing maps. */
export function errorsKey(err: unknown): string | null {
  const key = apiErrorKey(err);
  if (!key) return null;
  return key.startsWith("Errors.") ? key.slice("Errors.".length) : key;
}
