// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";
import { useEffect, useState } from "react";

import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { deliverabilityCounts } from "@/lib/courier";
import { checkServiceability } from "@/lib/geo";

export type DeliverabilityStatus =
  | "loading"
  | "needs_location"
  | "fallback"
  | "courier_only"
  | "deliverable";

interface Resolved {
  key: string;
  // local store count for `key`; -1 marks a failed check (treated as loading)
  local: number;
  courier: number;
}

/**
 * Resolves the visitor's deliverability state for the overview views:
 * - `loading`        — context not hydrated, or the check for the current location is in flight
 * - `needs_location` — no real location is known (do NOT show Mumbai's stores)
 * - `fallback`       — location known but no store delivers or ships here
 * - `courier_only`   — no store delivers here, but at least one ships by courier
 * - `deliverable`    — location known and at least one store delivers
 *
 * Local `store_count === 0` with no courier store is the single fallback
 * trigger, matching "no stores are available for delivery in your area".
 */
export function useDeliverability(): {
  status: DeliverabilityStatus;
  storeCount: number;
  courierStoreCount: number;
} {
  const { location, hydrated, userSet } = useDeliveryLocation();
  const [resolved, setResolved] = useState<Resolved | null>(null);
  const key = `${location.lat},${location.lng}`;

  useEffect(() => {
    if (!hydrated || !userSet) return;
    let cancelled = false;
    checkServiceability(location.lat, location.lng)
      .then((r) => {
        if (!cancelled) setResolved({ key, ...deliverabilityCounts(r) });
      })
      .catch(() => {
        if (!cancelled) setResolved({ key, local: -1, courier: 0 });
      });
    return () => {
      cancelled = true;
    };
  }, [hydrated, userSet, key, location.lat, location.lng]);

  const none = { storeCount: 0, courierStoreCount: 0 };
  if (!hydrated) return { status: "loading", ...none };
  if (!userSet) return { status: "needs_location", ...none };
  // No result yet, or a result for a previous location → still resolving.
  if (resolved === null || resolved.key !== key || resolved.local < 0) {
    return { status: "loading", ...none };
  }
  const counts = { storeCount: resolved.local, courierStoreCount: resolved.courier };
  if (resolved.local > 0) return { status: "deliverable", ...counts };
  if (resolved.courier > 0) return { status: "courier_only", ...counts };
  return { status: "fallback", ...none };
}
