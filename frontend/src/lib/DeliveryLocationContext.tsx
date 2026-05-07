"use client";

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
  location: DeliveryLocation | null;
  setLocation: (loc: DeliveryLocation | null) => void;
  clear: () => void;
}

const STORAGE_KEY = "kb_delivery_location";

const DeliveryLocationContext =
  createContext<DeliveryLocationContextValue | null>(null);

export function DeliveryLocationProvider(
  { children }: { children: React.ReactNode },
) {
  const [location, setLocationState] = useState<DeliveryLocation | null>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setLocationState(JSON.parse(raw));
    } catch {
      // localStorage unavailable / corrupted JSON — ignore.
    }
  }, []);

  const setLocation = useCallback((loc: DeliveryLocation | null) => {
    setLocationState(loc);
    if (typeof window === "undefined") return;
    if (loc) localStorage.setItem(STORAGE_KEY, JSON.stringify(loc));
    else localStorage.removeItem(STORAGE_KEY);
  }, []);

  const clear = useCallback(() => setLocation(null), [setLocation]);

  const value = useMemo(
    () => ({ location, setLocation, clear }),
    [location, setLocation, clear],
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
