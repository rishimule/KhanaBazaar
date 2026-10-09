// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Indian mobile numbers on the customer signup screens (spec 2026-10-08).
 *
 * The field holds digits only; `+91` is a fixed prefix. The backend
 * (`core.otp.normalize_phone`) stays the authority — these helpers only keep
 * what the customer typed or pasted in a shape it can check.
 */

export const INDIAN_PHONE_PREFIX = "+91";

/** "0091" + 10 national digits — the longest form a customer might type. */
const MAX_TYPED_DIGITS = 14;

/** Zero code points of the decimal digit blocks an Indian phone keypad may
 * produce (Devanagari, Bengali, Gurmukhi, Gujarati, Oriya, Tamil, Telugu,
 * Kannada, Malayalam) plus full-width digits. */
const DIGIT_ZEROS = [
  0x0966, 0x09e6, 0x0a66, 0x0ae6, 0x0b66, 0x0be6, 0x0c66, 0x0ce6, 0x0d66, 0xff10,
];

function toAsciiDigits(raw: string): string {
  let out = "";
  for (const ch of raw) {
    const code = ch.codePointAt(0) ?? 0;
    const zero = DIGIT_ZEROS.find((z) => code >= z && code <= z + 9);
    out += zero === undefined ? ch : String(code - zero);
  }
  return out;
}

/** Only the digits of `raw`, as ASCII — for one-time-code inputs, so a
 * customer typing on an Indic keypad isn't left with an empty field. */
export function asciiDigits(raw: string): string {
  return toAsciiDigits(raw).replace(/[^0-9]/g, "");
}

/** Typed or pasted text → its digits, with a country or trunk prefix
 * dropped only when exactly 10 national digits remain (11 digits starting
 * 0, 12 starting 91, 13 starting 091 or 910, 14 starting 0091). Anything
 * else is kept as typed and simply fails validation — never silently
 * truncated, which would turn a key-by-key `+919876543210` into the
 * valid-looking `9198765432`. Past 14 digits the value is capped at 15, so
 * it stays visibly too long instead of becoming some other number. */
export function nationalDigits(raw: string): string {
  const d = asciiDigits(raw);
  if (d.length > MAX_TYPED_DIGITS) return d.slice(0, MAX_TYPED_DIGITS + 1);
  if (d.length === 11 && d.startsWith("0")) return d.slice(1);
  if (d.length === 12 && d.startsWith("91")) return d.slice(2);
  if (d.length === 13 && (d.startsWith("091") || d.startsWith("910"))) return d.slice(3);
  if (d.length === 14 && d.startsWith("0091")) return d.slice(4);
  return d;
}

export function isValidIndianMobile(digits: string): boolean {
  return /^[6-9][0-9]{9}$/.test(digits);
}

export function toE164(digits: string): string {
  return `${INDIAN_PHONE_PREFIX}${digits}`;
}

/** `+919876543210` or `9876543210` → `+91 98765 43210` (display only). */
export function formatIndianMobile(phone: string): string {
  const digits = nationalDigits(phone);
  if (digits.length !== 10) return phone;
  return `${INDIAN_PHONE_PREFIX} ${digits.slice(0, 5)} ${digits.slice(5)}`;
}
