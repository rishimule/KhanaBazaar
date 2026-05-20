"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useRef } from "react";

import { useAuth } from "@/lib/AuthContext";
import { useCustomerAddresses } from "@/lib/CustomerAddressesContext";
import {
  isDefaultDeliveryLocation,
  useDeliveryLocation,
} from "@/lib/DeliveryLocationContext";
import { formatAddress } from "@/lib/format-address";
import { truncateLabel } from "@/lib/geo";
import type { CustomerAddress } from "@/types";

function pickAutoSyncAddress(
  defaultAddress: CustomerAddress | null,
  addresses: CustomerAddress[],
): CustomerAddress | null {
  const hasCoords = (a: CustomerAddress) =>
    a.address.latitude != null && a.address.longitude != null;
  if (defaultAddress && hasCoords(defaultAddress)) return defaultAddress;
  return addresses.find(hasCoords) ?? null;
}

/** Side-effect-only component. Runs once per (token, dbUser.id) when the
 *  logged-in customer's stored DeliveryLocation is still the Mumbai fallback,
 *  setting it to their default saved address. Renders nothing. */
export function DeliveryLocationAutoSync() {
  const auth = useAuth();
  const { location, hydrated, setLocation } = useDeliveryLocation();
  const { addresses, defaultAddress, loading } = useCustomerAddresses();
  const didSyncRef = useRef(false);

  // Reset the one-shot when the identity changes so a second customer
  // signing in on the same tab also gets auto-synced.
  useEffect(() => {
    didSyncRef.current = false;
  }, [auth.token, auth.dbUser?.id]);

  useEffect(() => {
    if (didSyncRef.current) return;
    if (auth.loading || !hydrated || loading) return;
    if (!auth.token || auth.dbUser?.role !== "customer") return;
    if (!isDefaultDeliveryLocation(location)) return;

    const target = pickAutoSyncAddress(defaultAddress, addresses);
    if (!target) return;
    if (target.address.latitude == null || target.address.longitude == null) return;

    setLocation({
      lat: target.address.latitude,
      lng: target.address.longitude,
      label: truncateLabel(formatAddress(target.address), 40),
    });
    didSyncRef.current = true;
  }, [
    auth.loading,
    auth.token,
    auth.dbUser?.role,
    hydrated,
    loading,
    location,
    defaultAddress,
    addresses,
    setLocation,
  ]);

  return null;
}
