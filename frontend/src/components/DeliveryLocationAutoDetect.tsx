// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";
import { useEffect, useRef } from "react";

import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { useDeviceLocation } from "@/lib/useDeviceLocation";

const ATTEMPT_KEY = "kb_geo_autodetect_attempted";

/**
 * Render-nothing side effect: on first load for a guest/customer with no real
 * delivery location yet, request the browser geolocation once. Guarded by a
 * per-device localStorage flag so we never re-prompt on subsequent loads.
 * Logged-in customers with a saved address get auto-synced first, so the
 * `!userSet` gate fails for them and this never prompts.
 */
export default function DeliveryLocationAutoDetect() {
  const { hydrated, userSet } = useDeliveryLocation();
  const { supported, request } = useDeviceLocation();
  const fired = useRef(false);

  useEffect(() => {
    if (fired.current) return;
    if (!hydrated || userSet || !supported) return;
    if (typeof window === "undefined") return;
    if (window.localStorage.getItem(ATTEMPT_KEY) === "1") return;
    fired.current = true;
    window.localStorage.setItem(ATTEMPT_KEY, "1");
    request();
  }, [hydrated, userSet, supported, request]);

  return null;
}
