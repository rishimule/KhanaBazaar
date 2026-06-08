// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Client-side validation for the seller profile edit modal
 * (ProfileChangeRequestModal). Mirrors the backend per-group Pydantic regex in
 * backend/app/src/app/schemas/seller_profile_change_request.py so the seller
 * gets friendly, inline feedback before a submit round-trip. Messages are
 * hard-coded English, matching the modal's existing hard-coded field labels.
 */
import { ApiError } from "@/lib/api";
import { phoneOtpErrorMessage } from "@/lib/sellerPhone";

// Regex copied from the backend schemas (keep in sync).
const GST_RE = /^[0-9A-Z]{15}$/;
const FSSAI_RE = /^[0-9]{14}$/;
const IFSC_RE = /^[A-Z]{4}0[A-Z0-9]{6}$/;
const BANK_ACCOUNT_RE = /^[0-9]{9,18}$/;

// Shared message strings, reused by validateField and changeRequestErrorMessage.
const MSG = {
  gst: "Enter a valid 15-character GSTIN (capital letters and digits, e.g. 06AAAAA1111A1Z1).",
  fssai: "FSSAI licence must be exactly 14 digits.",
  account: "Account number must be 9 to 18 digits.",
  ifsc: "Enter a valid IFSC code, e.g. HDFC0000001.",
  phone: "Enter a valid Indian mobile number (10 digits starting 6–9).",
  tooLong: "Keep this under 200 characters.",
  fullNameRequired: "Enter the owner's full name.",
  businessNameRequired: "Enter the business name.",
  submitFailed: "Couldn't submit your changes. Please try again.",
} as const;

/**
 * Transform a field's value as the user types. Uppercases GST and IFSC (the
 * backend requires capitals, so lowercase input would falsely fail). Does NOT
 * trim — trimming live would block spaces while typing a business name;
 * trimming happens in validateField and at submit time instead.
 */
export function normalizeField(field: string, value: string): string {
  if (field === "gst_number" || field === "bank_ifsc") return value.toUpperCase();
  return value;
}

/**
 * Validate one field. Returns a friendly English message, or null when valid.
 * Legal/banking fields are optional: an empty value is valid (lets a seller
 * clear the field), a non-empty value must match the format. Identity names
 * are required and capped at 200 chars. Fields not listed (phone, address,
 * delivery_radius_km) return null — they are validated by their own flows.
 */
export function validateField(field: string, value: string): string | null {
  const v = value.trim();
  switch (field) {
    case "full_name":
      if (v.length === 0) return MSG.fullNameRequired;
      if (v.length > 200) return MSG.tooLong;
      return null;
    case "business_name":
      if (v.length === 0) return MSG.businessNameRequired;
      if (v.length > 200) return MSG.tooLong;
      return null;
    case "gst_number":
      return v === "" || GST_RE.test(v) ? null : MSG.gst;
    case "fssai_license":
      return v === "" || FSSAI_RE.test(v) ? null : MSG.fssai;
    case "bank_account_number":
      return v === "" || BANK_ACCOUNT_RE.test(v) ? null : MSG.account;
    case "bank_ifsc":
      return v === "" || IFSC_RE.test(v) ? null : MSG.ifsc;
    default:
      return null;
  }
}

/**
 * Map a change-request submit error to a friendly sentence. Phone/OTP errors
 * (object-shaped detail or `phone_taken`) delegate to phoneOtpErrorMessage;
 * format and business-rule codes are mapped explicitly; anything else falls
 * back to the error message or a generic line.
 */
export function changeRequestErrorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (typeof e.detail === "object" || e.detail === "phone_taken") {
      return phoneOtpErrorMessage(e);
    }
    switch (e.detail) {
      case "gst_number format invalid":
        return MSG.gst;
      case "fssai_license format invalid":
        return MSG.fssai;
      case "bank_account_number format invalid":
        return MSG.account;
      case "bank_ifsc format invalid":
        return MSG.ifsc;
      case "phone format invalid":
        return MSG.phone;
      case "cr_already_open":
        return "You already have a pending change for this section. Review or withdraw it first.";
      case "seller_not_active":
        return "Your store isn't approved yet, so changes can't be submitted.";
      case "phone_verification_required":
        return "Verify your new phone number before submitting.";
      case "phone_verification_mismatch":
        return "The verified phone doesn't match. Re-verify and try again.";
      default:
        return e.message || MSG.submitFailed;
    }
  }
  return e instanceof Error ? e.message : MSG.submitFailed;
}
