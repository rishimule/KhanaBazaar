// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "@/lib/AuthContext";
import {
  SELLER_ORDER_SOUND_KEY,
  getSellerOrderAlertSummary,
  playNewOrderChime,
  primeAudio,
} from "@/lib/sellerOrderAlerts";

const POLL_MS = 30_000;

export interface SellerOrderAlertsState {
  /** null = unknown (not loaded yet, or the fetch failed). Never coerce to 0. */
  pendingCount: number | null;
  newOrderId: number | null;
  dismissNewOrder: () => void;
  soundEnabled: boolean;
  setSoundEnabled: (on: boolean) => void;
}

export function useSellerOrderAlerts(): SellerOrderAlertsState {
  const { token } = useAuth();
  const [pendingCount, setPendingCount] = useState<number | null>(null);
  const [newOrderId, setNewOrderId] = useState<number | null>(null);
  const [soundEnabled, setSoundEnabledState] = useState(false);
  const lastSeenRef = useRef<number | null>(null);
  // Distinct from `lastSeenRef === null`: a seller with an EMPTY queue gets
  // latest_pending_order_id === null, so the ref alone can't tell "never polled"
  // from "nothing pending". Without this flag the very first order after an
  // empty queue would be mistaken for pre-existing backlog and never alert.
  const seededRef = useRef(false);
  const soundRef = useRef(false);

  // Restore the per-device sound preference.
  useEffect(() => {
    const stored = window.localStorage.getItem(SELLER_ORDER_SOUND_KEY) === "1";
    soundRef.current = stored;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time localStorage hydration
    setSoundEnabledState(stored);
  }, []);

  const setSoundEnabled = useCallback((on: boolean) => {
    soundRef.current = on;
    setSoundEnabledState(on);
    window.localStorage.setItem(SELLER_ORDER_SOUND_KEY, on ? "1" : "0");
    // The enabling click is the user gesture that unlocks the AudioContext.
    if (on) primeAudio();
  }, []);

  const dismissNewOrder = useCallback(() => setNewOrderId(null), []);

  const tick = useCallback(async () => {
    if (!token) return;
    try {
      const res = await getSellerOrderAlertSummary(token);
      setPendingCount(res.pending_count);
      const latest = res.latest_pending_order_id;
      if (!seededRef.current) {
        // The first successful response seeds the baseline (even when it is
        // null) — a pre-existing backlog must never alert on page load.
        seededRef.current = true;
        lastSeenRef.current = latest;
      } else if (
        latest !== null &&
        (lastSeenRef.current === null || latest > lastSeenRef.current)
      ) {
        lastSeenRef.current = latest;
        setNewOrderId(latest);
        if (soundRef.current) playNewOrderChime();
        if (typeof navigator !== "undefined" && navigator.vibrate) {
          navigator.vibrate([200, 100, 200]);
        }
      }
    } catch {
      // Unknown, not zero — the badge hides rather than lying about the count.
      // The last-seen baseline is deliberately left intact so a flaky poll
      // can't replay an old order as "new" on the next success.
      setPendingCount(null);
    }
  }, [token]);

  useEffect(() => {
    if (!token) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- tick() is async; every setState lands after the network await, not synchronously in the effect
    void tick();
    const iv = setInterval(() => void tick(), POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void tick();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      clearInterval(iv);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [token, tick]);

  return {
    pendingCount,
    newOrderId,
    dismissNewOrder,
    soundEnabled,
    setSoundEnabled,
  };
}
