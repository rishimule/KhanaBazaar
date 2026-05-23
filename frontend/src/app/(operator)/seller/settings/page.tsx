"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/AuthContext";
import { get, patch } from "@/lib/api";
import type { Store } from "@/types";
import styles from "./page.module.css";

const MIN_KM = 0.5;
const MAX_KM = 50;
const STEP_KM = 0.5;

function clamp(km: number): number {
  const rounded = Math.round(km / STEP_KM) * STEP_KM;
  return Math.max(MIN_KM, Math.min(MAX_KM, rounded));
}

export default function SellerSettingsPage() {
  const { token } = useAuth();
  const [store, setStore] = useState<Store | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingRadius, setSavingRadius] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<number | null>(null);
  // Monotonic request id — drop stale PATCH responses that resolve after a newer one.
  const reqIdRef = useRef(0);

  useEffect(() => {
    if (!token) return;
    get<Store[]>("/api/v1/stores/my", token)
      .then((stores) => {
        if (stores.length > 0) setStore(stores[0]);
      })
      .catch(() => setError("Could not load store."))
      .finally(() => setLoading(false));
  }, [token]);

  const persistRadius = (km: number) => {
    if (!store || !token) return;
    const myReq = ++reqIdRef.current;
    setSavingRadius(true);
    patch<Store>(`/api/v1/stores/${store.id}`, { delivery_radius_km: km }, token)
      .then((updated) => {
        if (myReq === reqIdRef.current) setStore(updated);
      })
      .catch(() => {
        if (myReq === reqIdRef.current) setError("Could not save delivery radius.");
      })
      .finally(() => {
        if (myReq === reqIdRef.current) setSavingRadius(false);
      });
  };

  const updateRadius = (km: number) => {
    if (!store) return;
    if (!Number.isFinite(km)) return;
    const next = clamp(km);
    setStore({ ...store, delivery_radius_km: next });
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => persistRadius(next), 350);
  };

  const bump = (delta: number) => {
    if (!store) return;
    updateRadius(store.delivery_radius_km + delta);
  };

  if (loading) return <div className={styles.empty}>Loading…</div>;
  if (!store) return <div className={styles.empty}>No store associated with this account.</div>;

  const coverage = Math.round(Math.PI * store.delivery_radius_km ** 2);

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Store settings</h1>

      {!store.pin_confirmed && (
        <div className={styles.pinBanner}>
          <strong>Pin not confirmed.</strong> Customers can&apos;t see your store on
          the map yet.{" "}
          <Link href="/seller/signup?resubmit=true" className={styles.bannerLink}>
            Drop your pin →
          </Link>
        </div>
      )}

      {error && <div className={styles.errorBanner}>{error}</div>}

      <section className={styles.card}>
        <header className={styles.cardHeader}>
          <h2 className={styles.cardTitle}>Delivery radius</h2>
          <p className={styles.cardCaption}>
            Customers further than this won&apos;t see your store. Covers about{" "}
            <strong>{coverage} sq km</strong> of area.
          </p>
        </header>
        <div className={styles.radiusRow}>
          <button
            type="button"
            className={styles.stepBtn}
            onClick={() => bump(-STEP_KM)}
            aria-label="Decrease radius"
            disabled={store.delivery_radius_km <= MIN_KM}
          >
            −
          </button>
          <input
            type="number"
            className={styles.radiusInput}
            min={MIN_KM}
            max={MAX_KM}
            step={STEP_KM}
            value={store.delivery_radius_km}
            onChange={(e) => updateRadius(parseFloat(e.target.value))}
            aria-label="Delivery radius in kilometres"
          />
          <span className={styles.unit}>km</span>
          <button
            type="button"
            className={styles.stepBtn}
            onClick={() => bump(STEP_KM)}
            aria-label="Increase radius"
            disabled={store.delivery_radius_km >= MAX_KM}
          >
            +
          </button>
          {savingRadius && <span className={styles.savingChip}>Saving…</span>}
        </div>
      </section>

      <section className={styles.card}>
        <header className={styles.cardHeader}>
          <h2 className={styles.cardTitle}>Store details</h2>
        </header>
        <dl className={styles.detailGrid}>
          <dt>Store name</dt>
          <dd>{store.name}</dd>
          <dt>Status</dt>
          <dd>{store.is_active ? "Active" : "Inactive"}</dd>
          <dt>Pin confirmed</dt>
          <dd>{store.pin_confirmed ? "Yes" : "No"}</dd>
        </dl>
      </section>

      <section className={styles.card}>
        <header className={styles.cardHeader}>
          <h2 className={styles.cardTitle}>Profile & services</h2>
        </header>
        <div className={styles.linkRow}>
          <Link href="/seller/signup?resubmit=true" className="btn btn-outline">
            Edit business profile
          </Link>
          <Link href={`/stores/${store.id}`} className="btn btn-outline">
            View storefront
          </Link>
        </div>
      </section>
    </div>
  );
}
