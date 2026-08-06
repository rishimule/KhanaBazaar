// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useEffect, useRef } from "react";

/** Both `visibilitychange` and `focus` fire on a single tab return; collapse
 *  re-entries inside this window into one call. */
const MIN_GAP_MS = 1_000;

/**
 * Run `onRefresh` when the tab becomes visible again or the window regains
 * focus — the moment a seller comes back after a new-order alert and must not
 * be shown stale data.
 *
 * `onRefresh` is held in a ref, so a caller passing an inline closure does not
 * re-register the listeners on every render.
 */
export function useVisibilityRefresh(onRefresh: () => void): void {
  const lastRunRef = useRef(0);
  const callbackRef = useRef(onRefresh);

  useEffect(() => {
    callbackRef.current = onRefresh;
  });

  useEffect(() => {
    const run = () => {
      if (document.visibilityState !== "visible") return;
      const now = Date.now();
      if (now - lastRunRef.current < MIN_GAP_MS) return;
      lastRunRef.current = now;
      callbackRef.current();
    };
    document.addEventListener("visibilitychange", run);
    window.addEventListener("focus", run);
    return () => {
      document.removeEventListener("visibilitychange", run);
      window.removeEventListener("focus", run);
    };
  }, []);
}
