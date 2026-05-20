"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
} from "react";

export interface DeliveryLocation {
  lat: number;
  lng: number;
  /** Truncated formatted address (≤40 chars) shown in the navbar chip. */
  label: string;
}

interface DeliveryLocationContextValue {
  location: DeliveryLocation;
  /** False until the initial localStorage hydration effect has completed. */
  hydrated: boolean;
  setLocation: (loc: DeliveryLocation | null) => void;
  clear: () => void;
}

const STORAGE_KEY = "kb_delivery_location";

/** Fallback delivery location until the customer picks one explicitly. */
export const DEFAULT_DELIVERY_LOCATION: DeliveryLocation = {
  lat: 19.0760,
  lng: 72.8777,
  label: "Mumbai, Maharashtra, India",
};

const DeliveryLocationContext =
  createContext<DeliveryLocationContextValue | null>(null);

export function DeliveryLocationProvider(
  { children }: { children: React.ReactNode },
) {
  const [location, setLocationState] = useState<DeliveryLocation>(
    DEFAULT_DELIVERY_LOCATION,
  );
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time hydration from localStorage on mount
      if (raw) setLocationState(JSON.parse(raw));
    } catch {
      // localStorage unavailable / corrupted JSON — ignore.
    }
    setHydrated(true);
    // Sync state when another tab — or our own AuthContext.logout — wipes
    // the key. Without this listener, state lingers in this tab and the
    // store list keeps showing the previous user's location.
    const onStorage = (e: StorageEvent) => {
      if (e.key !== STORAGE_KEY) return;
      if (!e.newValue) {
        setLocationState(DEFAULT_DELIVERY_LOCATION);
        return;
      }
      try {
        setLocationState(JSON.parse(e.newValue));
      } catch {
        setLocationState(DEFAULT_DELIVERY_LOCATION);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const setLocation = useCallback((loc: DeliveryLocation | null) => {
    setLocationState(loc ?? DEFAULT_DELIVERY_LOCATION);
    if (typeof window === "undefined") return;
    if (loc) localStorage.setItem(STORAGE_KEY, JSON.stringify(loc));
    else localStorage.removeItem(STORAGE_KEY);
  }, []);

  const clear = useCallback(() => setLocation(null), [setLocation]);

  const value = useMemo(
    () => ({ location, hydrated, setLocation, clear }),
    [location, hydrated, setLocation, clear],
  );

  return (
    <DeliveryLocationContext.Provider value={value}>
      {children}
    </DeliveryLocationContext.Provider>
  );
}

export function useDeliveryLocation(): DeliveryLocationContextValue {
  const ctx = useContext(DeliveryLocationContext);
  if (!ctx) {
    throw new Error(
      "useDeliveryLocation must be used inside DeliveryLocationProvider",
    );
  }
  return ctx;
}

/** Imperative localStorage clear for callers outside React (e.g. AuthContext
 *  logout). Use the hook inside React components instead. */
export function clearStoredDeliveryLocation(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(STORAGE_KEY);
}

/** True when `loc` is exactly the Mumbai fallback. Used by
 *  DeliveryLocationAutoSync to decide whether to overwrite. */
export function isDefaultDeliveryLocation(loc: DeliveryLocation): boolean {
  return (
    loc.lat === DEFAULT_DELIVERY_LOCATION.lat &&
    loc.lng === DEFAULT_DELIVERY_LOCATION.lng &&
    loc.label === DEFAULT_DELIVERY_LOCATION.label
  );
}
