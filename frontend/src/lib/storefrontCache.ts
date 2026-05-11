// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { get } from "@/lib/api";
import type { StorefrontResponse } from "@/types";

/* Stale-while-revalidate cache for the storefront endpoint. Keyed by
 * `(storeId, locale)` because translations vary per locale and the
 * server returns localized names inline.
 *
 * The store-detail page hits this on mount. Re-navigating back into the
 * same store within the TTL returns cached data synchronously and skips
 * the spinner. Past the TTL, cached data renders immediately while a
 * background revalidate refreshes it.
 *
 * In-memory, single-tab. Cleared on hard refresh. No persistence —
 * stale-price risk past TTL is bounded, and checkout revalidates
 * inventory transactionally anyway.
 */

const TTL_MS = 60_000;

interface Entry {
  data: StorefrontResponse;
  expiresAt: number;
  // In-flight revalidation promise. Multiple subscribers wait on the
  // same fetch instead of dog-piling the backend.
  pending?: Promise<StorefrontResponse>;
}

const cache = new Map<string, Entry>();
const inFlight = new Map<string, Promise<StorefrontResponse>>();

function cacheKey(storeId: number, locale: string): string {
  return `${storeId}::${locale}`;
}

async function fetchStorefront(
  storeId: number,
  locale: string,
): Promise<StorefrontResponse> {
  // Backend reads locale from Accept-Language; the api wrapper attaches
  // the current next-intl locale automatically, so no need to send a
  // query param here. The `locale` arg only namespaces the cache.
  void locale;
  return get<StorefrontResponse>(`/api/v1/stores/${storeId}/storefront`);
}

/** Get the cached entry if it has not expired. */
export function readCachedStorefront(
  storeId: number,
  locale: string,
): StorefrontResponse | null {
  const entry = cache.get(cacheKey(storeId, locale));
  if (!entry) return null;
  if (entry.expiresAt <= Date.now()) return null;
  return entry.data;
}

/** Get any cached entry, fresh or stale. Used to paint instantly while
 * a background revalidate refreshes the data. */
export function readStaleStorefront(
  storeId: number,
  locale: string,
): StorefrontResponse | null {
  const entry = cache.get(cacheKey(storeId, locale));
  return entry ? entry.data : null;
}

/** Warm the cache without throwing. Intended for `onMouseEnter` /
 * `onFocus` / `onTouchStart` handlers on store cards — by the time the
 * user clicks the link, the storefront has usually finished loading and
 * the next page can paint synchronously from cache. Idempotent and
 * cheap: if a fetch is already in flight or the data is fresh, this is
 * a no-op.
 */
export function prefetchStorefront(storeId: number, locale: string): void {
  if (readCachedStorefront(storeId, locale)) return;
  loadStorefront(storeId, locale).catch(() => {
    // Swallow — this is a speculative prefetch. The eventual real fetch
    // on the destination page will surface any error.
  });
}

export async function loadStorefront(
  storeId: number,
  locale: string,
): Promise<StorefrontResponse> {
  const key = cacheKey(storeId, locale);
  const existing = inFlight.get(key);
  if (existing) return existing;

  const promise = (async () => {
    try {
      const data = await fetchStorefront(storeId, locale);
      cache.set(key, { data, expiresAt: Date.now() + TTL_MS });
      return data;
    } finally {
      inFlight.delete(key);
    }
  })();
  inFlight.set(key, promise);
  return promise;
}

/** Imperative invalidate hook, e.g. for after the seller updates stock
 * from another tab — currently unused but cheap to keep available. */
export function invalidateStorefront(storeId: number, locale?: string): void {
  if (locale) {
    cache.delete(cacheKey(storeId, locale));
    return;
  }
  for (const key of [...cache.keys()]) {
    if (key.startsWith(`${storeId}::`)) cache.delete(key);
  }
}
