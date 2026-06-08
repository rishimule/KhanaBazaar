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

// Shared message strings, reused by validateField and profileEditErrorMessage.
const MSG = {
  gst: "Enter a valid 15-character GSTIN (capital letters and digits, e.g. 06AAAAA1111A1Z1).",
  fssai: "FSSAI license must be exactly 14 digits.",
  account: "Account number must be 9 to 18 digits.",
  ifsc: "Enter a valid IFSC code, e.g. HDFC0000001.",
  phone: "Enter a valid Indian mobile number (10 digits starting 6–9).",
  tooLong: "Keep this under 200 characters.",
  fullNameRequired: "Enter the owner's full name.",
  businessNameRequired: "Enter the business name.",
  etaOrder: "Maximum delivery time must be at least the minimum.",
  checkEntries: "Please check your entries and try again.",
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
 * Pull a usable { msg, field } out of an ApiError.detail, which may be:
 *  - a FastAPI 422 envelope (array of {type, loc, msg}) from the inline PATCH
 *    endpoints — take the first item; strip Pydantic's "Value error, " prefix;
 *    field = last loc segment;
 *  - a plain string (the change-request path extracts one message string);
 *  - anything else → empty.
 */
function extractDetail(detail: unknown): { msg: string; field: string } {
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as Record<string, unknown>;
    let msg = typeof first.msg === "string" ? first.msg : "";
    const prefix = "Value error, ";
    if (msg.startsWith(prefix)) msg = msg.slice(prefix.length);
    const loc = Array.isArray(first.loc) ? first.loc : [];
    const field = loc.length > 0 ? String(loc[loc.length - 1]) : "";
    return { msg, field };
  }
  if (typeof detail === "string") return { msg: detail, field: "" };
  return { msg: "", field: "" };
}

/**
 * Map any profile-edit backend error to friendly English. Used by both the
 * change-request modal (string detail) and the inline direct-PATCH edits
 * (FastAPI 422 list detail). Phone/OTP errors (object detail or `phone_taken`)
 * delegate to phoneOtpErrorMessage. `fallback` is shown when nothing specific
 * matches (callers pass a context line for network/unknown failures).
 */
export function profileEditErrorMessage(e: unknown, fallback?: string): string {
  if (!(e instanceof ApiError)) {
    if (e instanceof Error && e.message) return e.message;
    return fallback ?? MSG.checkEntries;
  }
  const d: unknown = e.detail;
  // OTP endpoints return object-shaped detail ({error, retry_after?}). Arrays
  // are objects too, so this MUST come after the array case — hence we check
  // "object but not array" here.
  if ((typeof d === "object" && d !== null && !Array.isArray(d)) || d === "phone_taken") {
    return phoneOtpErrorMessage(e);
  }
  const { msg, field } = extractDetail(d);
  switch (msg) {
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
    case "pincode must be 6 digits with no leading zero for India":
      return "Enter a valid 6-digit pincode.";
    case "state must be an Indian state or Union Territory":
      return "Choose a valid Indian state or Union Territory.";
    case "duplicate service_id rows":
      return "You've selected the same service twice.";
    case "delivery_eta_max_minutes must be >= delivery_eta_min_minutes":
    case "delivery_eta_min_minutes must be <= delivery_eta_max_minutes":
      return MSG.etaOrder;
    case "delivery_eta_min_minutes and delivery_eta_max_minutes must be set together":
      return "Set both the minimum and maximum delivery times.";
    case "use_change_request":
      return "This change needs admin approval — use Edit to submit it for review.";
    case "cr_already_open":
      return "You already have a pending change for this section. Review or withdraw it first.";
    case "cr_not_resubmittable":
      return "This request can no longer be resubmitted. Start a new change instead.";
    case "cr_not_open":
      return "This request is no longer open for changes.";
    case "seller_not_active":
      return "Your store isn't approved yet, so changes can't be submitted.";
    case "phone_verification_required":
      return "Verify your new phone number before submitting.";
    case "phone_verification_mismatch":
      return "The verified phone doesn't match. Re-verify and try again.";
  }
  switch (field) {
    case "delivery_radius_km":
      return "Delivery radius must be 50 km or less.";
    case "min_order_value":
      return "Minimum order value must be between ₹0 and ₹1,00,000.";
    case "delivery_eta_min_minutes":
    case "delivery_eta_max_minutes":
      return "Delivery time must be between 1 and 20160 minutes.";
  }
  return fallback ?? MSG.checkEntries;
}
