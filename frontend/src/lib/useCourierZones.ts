"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useEffect, useState } from "react";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { checkServiceability, type ServiceabilityResult } from "@/lib/geo";

const TTL_MS = 2 * 60 * 1000;
const MAX_ENTRIES = 100;
const cache = new Map<string, { at: number; result: Promise<ServiceabilityResult> }>();

/** Store pages and the cart ask the same question on every visit. Sharing an
 *  answer for a couple of minutes keeps browsing from eating the per-IP geo
 *  budget (30/min) that checkout's address checks draw on too. Failures are
 *  never cached, so the next visit simply asks again. */
function cachedServiceability(
  lat: number,
  lng: number,
  storeId: number,
): Promise<ServiceabilityResult> {
  const key = `${lat},${lng}|${storeId}`;
  const now = Date.now();
  const hit = cache.get(key);
  if (hit && now - hit.at < TTL_MS) return hit.result;
  const result = checkServiceability(lat, lng, storeId);
  cache.delete(key);
  cache.set(key, { at: now, result });
  if (cache.size > MAX_ENTRIES) {
    const oldest = cache.keys().next().value;
    if (oldest !== undefined) cache.delete(oldest);
  }
  result.catch(() => {
    if (cache.get(key)?.result === result) cache.delete(key);
  });
  return result;
}

/**
 * Each store's zone for the navbar delivery location (store-page banner, cart
 * hint). Only for a location the customer actually chose — the Mumbai
 * fallback would invent a courier banner for someone who never said where
 * they are. A failed check is simply absent, never "doesn't ship here".
 *
 * A preview only: the checkout address decides the real delivery mode.
 */
export function useCourierZones(storeIds: number[]): Record<number, ServiceabilityResult> {
  const { location, hydrated, userSet } = useDeliveryLocation();
  const [state, setState] = useState<{
    key: string;
    byStore: Record<number, ServiceabilityResult>;
  }>({ key: "", byStore: {} });
  const idsKey = Array.from(new Set(storeIds))
    .sort((a, b) => a - b)
    .join(",");
  const key = hydrated && userSet && idsKey ? `${location.lat},${location.lng}|${idsKey}` : "";

  useEffect(() => {
    if (!key) return;
    let cancelled = false;
    const ids = idsKey.split(",").map(Number);
    Promise.all(
      ids.map((id) =>
        cachedServiceability(location.lat, location.lng, id)
          .then((r) => [id, r] as const)
          .catch(() => null),
      ),
    ).then((entries) => {
      if (cancelled) return;
      const byStore: Record<number, ServiceabilityResult> = {};
      for (const e of entries) if (e) byStore[e[0]] = e[1];
      setState({ key, byStore });
    });
    return () => {
      cancelled = true;
    };
  }, [key, idsKey, location.lat, location.lng]);

  // Results for an earlier location or store set are stale — show nothing.
  return state.key === key ? state.byStore : {};
}
