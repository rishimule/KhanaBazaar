"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import {
  createContext, useContext, useEffect, useMemo, useState,
} from "react";

import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import type { CustomerAddress, CustomerProfile } from "@/types";

interface CustomerAddressesContextValue {
  /** Full list as returned by the API, already sorted desc(is_default), id. */
  addresses: CustomerAddress[];
  /** First address with is_default === true, else null. */
  defaultAddress: CustomerAddress | null;
  /** True while a fetch is in flight. False once the first attempt settles. */
  loading: boolean;
  /** Human-readable error from the last fetch attempt, else null. */
  error: string | null;
}

const CustomerAddressesContext =
  createContext<CustomerAddressesContextValue | null>(null);

export function CustomerAddressesProvider(
  { children }: { children: React.ReactNode },
) {
  const auth = useAuth();
  const [addresses, setAddresses] = useState<CustomerAddress[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const role = auth.dbUser?.role ?? null;
  const token = auth.token;
  const authLoading = auth.loading;

  useEffect(() => {
    if (authLoading) return;
    if (!token || role !== "customer") {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reset stale state when auth identity changes
      setAddresses([]);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    get<CustomerProfile>("/api/v1/customers/me", token)
      .then((profile) => {
        if (cancelled) return;
        setAddresses(profile.addresses);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load addresses");
        setAddresses([]);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [token, role, authLoading]);

  const defaultAddress = useMemo(
    () => addresses.find((a) => a.is_default) ?? null,
    [addresses],
  );

  const value = useMemo<CustomerAddressesContextValue>(
    () => ({ addresses, defaultAddress, loading, error }),
    [addresses, defaultAddress, loading, error],
  );

  return (
    <CustomerAddressesContext.Provider value={value}>
      {children}
    </CustomerAddressesContext.Provider>
  );
}

export function useCustomerAddresses(): CustomerAddressesContextValue {
  const ctx = useContext(CustomerAddressesContext);
  if (!ctx) {
    throw new Error(
      "useCustomerAddresses must be used inside CustomerAddressesProvider",
    );
  }
  return ctx;
}
