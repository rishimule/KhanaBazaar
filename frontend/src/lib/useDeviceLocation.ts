"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useCallback, useState } from "react";

import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { reverseGeocode, truncateLabel } from "@/lib/geo";

export type DeviceLocationStatus =
  | "idle"
  | "unsupported"
  | "locating"
  | "resolving"
  | "done"
  | "denied"
  | "outside_india"
  | "error";

export interface UseDeviceLocationResult {
  status: DeviceLocationStatus;
  /** Trigger the browser permission prompt + resolve flow. Safe to call any time. */
  request: () => void;
  /** Reset status back to idle (e.g. when reopening a closed picker). */
  reset: () => void;
  /** True only when geolocation can actually run here: secure context + API present. */
  supported: boolean;
}

/** navigator.geolocation EXISTS on insecure origins but calls fail, so we must
 *  also check window.isSecureContext — object presence alone is not enough. */
function geolocationSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    window.isSecureContext &&
    typeof navigator !== "undefined" &&
    "geolocation" in navigator
  );
}

/**
 * Device-geolocation → DeliveryLocationContext bridge. Used by the
 * NearbyLocationBanner and the DeliveryLocationPicker "Use my location" button.
 *
 * Flow: secure-context check → getCurrentPosition → reverseGeocode → assert the
 * country component is India → setLocation(device coords + reverse-geocoded
 * label). On ANY failure the delivery location is left untouched (Mumbai
 * fallback for a fresh guest); the hook never throws.
 */
export function useDeviceLocation(): UseDeviceLocationResult {
  const { setLocation } = useDeliveryLocation();
  const [status, setStatus] = useState<DeviceLocationStatus>("idle");

  const reset = useCallback(() => setStatus("idle"), []);

  const request = useCallback(() => {
    if (!geolocationSupported()) {
      setStatus("unsupported");
      return;
    }
    setStatus("locating");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords;
        setStatus("resolving");
        reverseGeocode(latitude, longitude)
          .then((place) => {
            const country = place.components.find((c) =>
              c.types.includes("country"),
            );
            if (!country || country.short_name !== "IN") {
              setStatus("outside_india");
              return;
            }
            // Store the precise device coords, label from reverse geocode.
            setLocation({
              lat: latitude,
              lng: longitude,
              label: truncateLabel(place.formatted_address),
            });
            setStatus("done");
          })
          .catch(() => setStatus("error"));
      },
      (err) => {
        setStatus(err.code === err.PERMISSION_DENIED ? "denied" : "error");
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
    );
  }, [setLocation]);

  return {
    status,
    request,
    reset,
    supported: geolocationSupported(),
  };
}
