"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  APIProvider,
  Map,
  useMap,
} from "@vis.gl/react-google-maps";

import { reverseGeocode, type GeoPlace } from "@/lib/geo";

import styles from "./MapPicker.module.css";

export interface MapPickerProps {
  initialLat?: number;
  initialLng?: number;
  /** When set, the map pans to this point. Useful when a parent
   *  autocomplete picks a place — the map should follow so the fixed
   *  pin lines up with the chosen location. The reverse-geocode that
   *  would normally fire after this pan is suppressed (the parent
   *  already has authoritative place data from the autocomplete). */
  target?: { lat: number; lng: number } | null;
  /** When true, render an inline note that the user must place the pin
   *  before continuing (used in the seller-signup wizard). */
  requirePin?: boolean;
  onPlace: (place: GeoPlace) => void;
  onError?: (msg: string) => void;
}

const DEFAULT_CENTER = { lat: 19.076, lng: 72.8777 };  // Mumbai

/** Watches map idle events and fires reverse-geocode for the new center.
 *  The pin itself is a fixed CSS overlay over the map (rendered by the
 *  parent) — only the map pans underneath it. The first idle (initial
 *  render) is suppressed so the user must explicitly pan before a place
 *  is staged. */
function CenterListener({
  onCenter,
  resolveTo,
  programmaticTarget,
}: {
  onCenter: (lat: number, lng: number) => void;
  resolveTo: { lat: number; lng: number } | null;
  /** Programmatic pan from the parent (e.g., autocomplete pick). The idle
   *  that follows this pan is suppressed so the parent's authoritative
   *  place data is not overwritten by a redundant reverse-geocode. */
  programmaticTarget: { lat: number; lng: number } | null;
}) {
  const map = useMap();
  const lastFiredRef = useRef<{ lat: number; lng: number } | null>(null);
  const skipFirstIdleRef = useRef<boolean>(true);

  // Pan when "Use my location" sets resolveTo. The resulting idle goes
  // through the normal reverse-geocode path.
  useEffect(() => {
    if (map && resolveTo) map.panTo(resolveTo);
  }, [map, resolveTo]);

  // Pan when the parent picks a place (autocomplete). Pre-seed
  // lastFiredRef so the resulting idle dedups and skips onCenter.
  useEffect(() => {
    if (!map || !programmaticTarget) return;
    lastFiredRef.current = { ...programmaticTarget };
    map.panTo(programmaticTarget);
  }, [map, programmaticTarget]);

  useEffect(() => {
    if (!map) return;
    const listener = map.addListener("idle", () => {
      const c = map.getCenter();
      if (!c) return;
      // First idle fires immediately after the map renders at the initial
      // center — that's not a user pan, so skip it. Subsequent idles are
      // the user actually moving the map.
      if (skipFirstIdleRef.current) {
        skipFirstIdleRef.current = false;
        lastFiredRef.current = { lat: c.lat(), lng: c.lng() };
        return;
      }
      const lat = c.lat();
      const lng = c.lng();
      // Suppress duplicate fires when the center hasn't actually moved
      // (rounded to ~1m so floating-point noise doesn't trigger a call).
      const prev = lastFiredRef.current;
      if (prev && Math.abs(prev.lat - lat) < 1e-5 && Math.abs(prev.lng - lng) < 1e-5) {
        return;
      }
      lastFiredRef.current = { lat, lng };
      onCenter(lat, lng);
    });
    return () => listener.remove();
  }, [map, onCenter]);

  return null;
}

export function MapPicker({
  initialLat,
  initialLng,
  target,
  requirePin = false,
  onPlace,
  onError,
}: MapPickerProps) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY ?? "";
  const initial = {
    lat: initialLat ?? DEFAULT_CENTER.lat,
    lng: initialLng ?? DEFAULT_CENTER.lng,
  };
  const [resolved, setResolved] = useState<boolean>(
    initialLat != null && initialLng != null,
  );
  const [panTarget, setPanTarget] = useState<{ lat: number; lng: number } | null>(null);

  const onCenter = useCallback(
    async (lat: number, lng: number) => {
      try {
        const place = await reverseGeocode(lat, lng);
        const country = place.components.find((c) => c.types.includes("country"));
        if (country && country.short_name !== "IN") {
          onError?.("KhanaBazaar serves India only");
          return;
        }
        setResolved(true);
        onPlace(place);
      } catch {
        onError?.("Could not resolve address from the map center");
      }
    },
    [onPlace, onError],
  );

  const useMyLocation = useCallback(() => {
    if (!navigator.geolocation) {
      onError?.("Geolocation not supported on this device");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (p) => setPanTarget({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => onError?.("Permission denied — drag the map to your location"),
    );
  }, [onError]);

  if (!apiKey) {
    return (
      <div className={styles.fallback}>
        Map unavailable. Enter the address manually above.
      </div>
    );
  }

  return (
    <APIProvider apiKey={apiKey}>
      <div className={styles.wrapper}>
        <button
          type="button"
          onClick={useMyLocation}
          className={styles.locBtn}
        >
          Use my location
        </button>
        <div className={styles.mapBox}>
          <Map
            defaultCenter={initial}
            defaultZoom={16}
            mapId="kb-map-picker"
            gestureHandling="greedy"
            disableDefaultUI={false}
            style={{ width: "100%", height: "100%" }}
          >
            <CenterListener
              onCenter={(lat, lng) => void onCenter(lat, lng)}
              resolveTo={panTarget}
              programmaticTarget={target ?? null}
            />
          </Map>
          {/* Fixed crosshair pin over the map center. Drag the map under it. */}
          <div className={styles.pinOverlay} aria-hidden="true">
            <div className={styles.pin}>📍</div>
          </div>
        </div>
        <p className={styles.hint}>
          Drag the map so the pin sits on your exact door.
          {requirePin && !resolved && (
            <> <span className={styles.required}>Pin location to continue.</span></>
          )}
        </p>
      </div>
    </APIProvider>
  );
}
