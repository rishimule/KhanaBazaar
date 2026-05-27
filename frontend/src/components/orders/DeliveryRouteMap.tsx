"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import { useEffect } from "react";
import {
  AdvancedMarker,
  APIProvider,
  Map,
  useMap,
  useMapsLibrary,
} from "@vis.gl/react-google-maps";

import styles from "./DeliveryRouteMap.module.css";

export interface DeliveryRouteMapProps {
  store: { lat: number; lng: number; label: string };
  customer: { lat: number; lng: number; label: string };
}

/** Pure visual-UX component: shows the store, the delivery address, and a
 *  STRAIGHT line between them. No road routing — straight-line is intentional
 *  to avoid Distance Matrix API spend. The polyline's pixel length on the
 *  rendered map is the "as the crow flies" distance, which is the same
 *  metric the backend's ST_DWithin gate uses anyway. */
function FitBounds({
  store, customer,
}: {
  store: { lat: number; lng: number };
  customer: { lat: number; lng: number };
}) {
  const map = useMap();
  useEffect(() => {
    if (!map) return;
    const bounds = new google.maps.LatLngBounds();
    bounds.extend({ lat: store.lat, lng: store.lng });
    bounds.extend({ lat: customer.lat, lng: customer.lng });
    map.fitBounds(bounds, 60);
  }, [map, store.lat, store.lng, customer.lat, customer.lng]);
  return null;
}

function StraightLine({
  store, customer,
}: {
  store: { lat: number; lng: number };
  customer: { lat: number; lng: number };
}) {
  const maps = useMapsLibrary("maps");
  const map = useMap();
  useEffect(() => {
    if (!maps || !map) return;
    const polyline = new maps.Polyline({
      path: [
        { lat: store.lat, lng: store.lng },
        { lat: customer.lat, lng: customer.lng },
      ],
      geodesic: true,
      strokeColor: "#e8611a",
      strokeOpacity: 0.9,
      strokeWeight: 4,
      map,
    });
    return () => {
      polyline.setMap(null);
    };
  }, [maps, map, store.lat, store.lng, customer.lat, customer.lng]);
  return null;
}

export function DeliveryRouteMap({ store, customer }: DeliveryRouteMapProps) {
  const t = useTranslations("Shared");
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY ?? "";
  if (!apiKey) {
    return (
      <div className={styles.fallback}>
        {t.rich("routeMap.unavailable", {
          code: (chunks) => <code>{chunks}</code>,
        })}
      </div>
    );
  }
  return (
    <APIProvider apiKey={apiKey}>
      <div className={styles.wrapper}>
        <div className={styles.mapBox}>
          <Map
            defaultCenter={{ lat: store.lat, lng: store.lng }}
            defaultZoom={13}
            mapId="kb-route-map"
            gestureHandling="cooperative"
            disableDefaultUI={false}
            style={{ width: "100%", height: "100%" }}
          >
            <FitBounds store={store} customer={customer} />
            <StraightLine store={store} customer={customer} />
            <AdvancedMarker position={{ lat: store.lat, lng: store.lng }} title={t("routeMap.markerStore", { label: store.label })}>
              <div className={styles.markerStore}>🏪</div>
            </AdvancedMarker>
            <AdvancedMarker position={{ lat: customer.lat, lng: customer.lng }} title={t("routeMap.markerDelivery", { label: customer.label })}>
              <div className={styles.markerCustomer}>📍</div>
            </AdvancedMarker>
          </Map>
        </div>
        <div className={styles.legend}>
          <span><span className={styles.markerIconStore} aria-hidden>🏪</span> {t("routeMap.legendStore")} {store.label}</span>
          <span><span className={styles.markerIconCustomer} aria-hidden>📍</span> {t("routeMap.legendDeliversTo")} {customer.label}</span>
        </div>
      </div>
    </APIProvider>
  );
}
