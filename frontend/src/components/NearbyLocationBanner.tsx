"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { useAuth } from "@/lib/AuthContext";
import { useCustomerAddresses } from "@/lib/CustomerAddressesContext";
import {
  isDefaultDeliveryLocation,
  useDeliveryLocation,
} from "@/lib/DeliveryLocationContext";
import { useDeviceLocation } from "@/lib/useDeviceLocation";

import styles from "./NearbyLocationBanner.module.css";

const DISMISS_KEY = "kb_geo_banner_dismissed";

/**
 * Slim, dismissible "Use your location for nearby stores" bar. Mounted on the
 * home + stores pages. Renders only while the delivery location is still the
 * Mumbai fallback (so it disappears the moment a real location is set) and only
 * for guests/customers in a secure context. Per-device dismissal persists in
 * localStorage and survives logout.
 */
export function NearbyLocationBanner() {
  const t = useTranslations("NearbyLocation");
  const { location, hydrated } = useDeliveryLocation();
  const { dbUser, loading } = useAuth();
  const { loading: addressesLoading } = useCustomerAddresses();
  const { status, request, supported } = useDeviceLocation();
  const [dismissed, setDismissed] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time client-mount gate (SSR safety)
    setMounted(true);
    try {
      if (localStorage.getItem(DISMISS_KEY) === "1") setDismissed(true);
    } catch {
      // localStorage unavailable — treat as not dismissed.
    }
  }, []);

  const onDismiss = () => {
    setDismissed(true);
    try {
      localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // ignore
    }
  };

  // Gate rendering. Order matters: SSR/hydration safety first.
  const role = dbUser?.role;
  const audienceOk = !role || role === "customer";
  if (!mounted || loading) return null; // avoid SSR mismatch + auth flicker
  if (!supported) return null; // insecure context / no geolocation API
  if (!audienceOk) return null; // sellers / admins never see it
  // Wait for a logged-in customer's saved-address auto-sync to settle before
  // deciding — otherwise the banner flashes during the /customers/me fetch for
  // customers who already have a usable saved address. (Guests resolve to
  // addressesLoading=false immediately, so they are unaffected.)
  if (role === "customer" && addressesLoading) return null;
  if (!hydrated) return null; // wait for location hydration to avoid flash
  if (!isDefaultDeliveryLocation(location)) return null; // already have a real location
  if (dismissed) return null;

  const busy = status === "locating" || status === "resolving";
  const errorMsg =
    status === "denied"
      ? t("denied")
      : status === "outside_india"
        ? t("outsideIndia")
        : status === "error"
          ? t("error")
          : null;

  return (
    <div className={styles.banner} role="region" aria-label={t("regionLabel")}>
      <span className={styles.icon} aria-hidden>
        📍
      </span>
      <span className={styles.text}>{t("bannerPrompt")}</span>
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.cta}
          onClick={request}
          disabled={busy}
        >
          {busy ? t("locating") : t("useMyLocation")}
        </button>
        <button
          type="button"
          className={styles.dismiss}
          aria-label={t("dismiss")}
          onClick={onDismiss}
        >
          ×
        </button>
      </div>
      {errorMsg && (
        <p className={styles.msg} role="alert">
          {errorMsg}
        </p>
      )}
    </div>
  );
}
