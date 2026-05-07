"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AdvancedMarker,
  APIProvider,
  Map,
  useMap,
} from "@vis.gl/react-google-maps";

import { reverseGeocode, type GeoPlace } from "@/lib/geo";

import styles from "./MapPicker.module.css";

export interface MapPickerProps {
  initialLat?: number;
  initialLng?: number;
  /** When true, render an inline note that the user must place the pin
   *  before continuing (used in the seller-signup wizard). */
  requirePin?: boolean;
  onPlace: (place: GeoPlace) => void;
  onError?: (msg: string) => void;
}

const DEFAULT_CENTER = { lat: 19.076, lng: 72.8777 };  // Mumbai

function PinController({
  pos, onPosChange,
}: {
  pos: { lat: number; lng: number };
  onPosChange: (lat: number, lng: number) => void;
}) {
  const map = useMap();

  useEffect(() => {
    if (map) map.panTo(pos);
  }, [map, pos]);

  return (
    <AdvancedMarker
      position={pos}
      draggable
      onDragEnd={(e) => {
        const ll = e.latLng;
        if (ll) onPosChange(ll.lat(), ll.lng());
      }}
    />
  );
}

export function MapPicker({
  initialLat,
  initialLng,
  requirePin = false,
  onPlace,
  onError,
}: MapPickerProps) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY ?? "";
  const [pos, setPos] = useState<{ lat: number; lng: number }>({
    lat: initialLat ?? DEFAULT_CENTER.lat,
    lng: initialLng ?? DEFAULT_CENTER.lng,
  });
  const [resolved, setResolved] = useState<boolean>(
    initialLat != null && initialLng != null,
  );

  const handleMove = useCallback(
    async (lat: number, lng: number) => {
      setPos({ lat, lng });
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
        onError?.("Could not resolve address from this pin");
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
      (p) => void handleMove(p.coords.latitude, p.coords.longitude),
      () => onError?.("Permission denied — drag pin to your location"),
    );
  }, [handleMove, onError]);

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
            defaultCenter={pos}
            defaultZoom={16}
            mapId="kb-map-picker"
            gestureHandling="greedy"
            disableDefaultUI={false}
            style={{ width: "100%", height: "100%" }}
          >
            <PinController pos={pos} onPosChange={(lat, lng) => void handleMove(lat, lng)} />
          </Map>
        </div>
        <p className={styles.hint}>
          Drag the pin to your exact door.
          {requirePin && !resolved && (
            <> <span className={styles.required}>Pin location to continue.</span></>
          )}
        </p>
      </div>
    </APIProvider>
  );
}
