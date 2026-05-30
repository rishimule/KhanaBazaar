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

export function apiErrorKey(err: unknown): string | null {
  if (!(err instanceof ApiError)) {
    if (err instanceof TypeError) return "Errors.network";
    return null;
  }

  const detail = typeof err.detail === "string" ? err.detail : "";
  const lower = detail.toLowerCase();

  // Detail-string matches that should win over the generic status fallback.
  if (lower === "service_unavailable") return "Errors.service_unavailable";
  if (lower === "service_mismatch") return "Errors.service_mismatch";
  if (lower === "store_paused" || lower === "service_paused")
    return "Errors.store_paused";

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
