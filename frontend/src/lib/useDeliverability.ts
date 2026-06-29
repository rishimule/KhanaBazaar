// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";
import { useEffect, useState } from "react";

import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { checkServiceability } from "@/lib/geo";

export type DeliverabilityStatus =
  | "loading"
  | "needs_location"
  | "fallback"
  | "deliverable";

interface Resolved {
  key: string;
  // store count for `key`; -1 marks a failed check (treated as loading)
  count: number;
}

/**
 * Resolves the visitor's deliverability state for the overview views:
 * - `loading`        — context not hydrated, or the check for the current location is in flight
 * - `needs_location` — no real location is known (do NOT show Mumbai's stores)
 * - `fallback`       — location known but zero stores deliver here
 * - `deliverable`    — location known and at least one store delivers
 *
 * `store_count === 0` is the single authoritative fallback trigger, matching
 * "no stores are available for delivery in your area".
 */
export function useDeliverability(): {
  status: DeliverabilityStatus;
  storeCount: number;
} {
  const { location, hydrated, userSet } = useDeliveryLocation();
  const [resolved, setResolved] = useState<Resolved | null>(null);
  const key = `${location.lat},${location.lng}`;

  useEffect(() => {
    if (!hydrated || !userSet) return;
    let cancelled = false;
    checkServiceability(location.lat, location.lng)
      .then((r) => {
        if (!cancelled) {
          setResolved({ key, count: r.store_count ?? (r.serviceable ? 1 : 0) });
        }
      })
      .catch(() => {
        if (!cancelled) setResolved({ key, count: -1 });
      });
    return () => {
      cancelled = true;
    };
  }, [hydrated, userSet, key, location.lat, location.lng]);

  if (!hydrated) return { status: "loading", storeCount: 0 };
  if (!userSet) return { status: "needs_location", storeCount: 0 };
  // No result yet, or a result for a previous location → still resolving.
  if (resolved === null || resolved.key !== key || resolved.count < 0) {
    return { status: "loading", storeCount: 0 };
  }
  if (resolved.count === 0) return { status: "fallback", storeCount: 0 };
  return { status: "deliverable", storeCount: resolved.count };
}
