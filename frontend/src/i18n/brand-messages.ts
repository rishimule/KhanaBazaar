// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { COMPANY_NAME } from "@/lib/brand";

function deepReplace(value: unknown): unknown {
  if (typeof value === "string") return value.replaceAll("{brand}", COMPANY_NAME);
  if (Array.isArray(value)) return value.map(deepReplace);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [
        k,
        deepReplace(v),
      ]),
    );
  }
  return value;
}

/**
 * Returns a copy of the messages tree with every `{brand}` token replaced by
 * COMPANY_NAME. Runs before next-intl compiles the strings, so `{brand}` never
 * needs to be a real ICU argument. Does not mutate the input (the cached import).
 */
export function applyBrandToMessages<T>(messages: T): T {
  return deepReplace(messages) as T;
}
