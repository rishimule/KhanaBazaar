"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useEffect, useState } from "react";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { checkServiceability, type ServiceabilityResult } from "@/lib/geo";

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
        checkServiceability(location.lat, location.lng, id)
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
