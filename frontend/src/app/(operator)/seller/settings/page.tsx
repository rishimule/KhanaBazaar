"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/AuthContext";
import { get, patch } from "@/lib/api";
import type { Service, Store } from "@/types";
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
  const [services, setServices] = useState<Service[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingRadius, setSavingRadius] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<number | null>(null);
  // Monotonic request id — drop stale PATCH responses that resolve after a newer one.
  const reqIdRef = useRef(0);
  const minReqRef = useRef<Record<number, number>>({});
  const minDebounceRef = useRef<Record<number, number>>({});

  useEffect(() => {
    if (!token) return;
    get<Store[]>("/api/v1/stores/my", token)
      .then((stores) => {
        if (stores.length > 0) setStore(stores[0]);
      })
      .catch(() => setError("Could not load store."))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    if (!token) return;
    get<{ services: Service[] }>("/api/v1/sellers/me/profile", token)
      .then((p) => setServices(p.services ?? []))
      .catch(() => {
        /* non-fatal; the minimum-order card just stays empty */
      });
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

  const persistMin = (serviceId: number, value: number) => {
    if (!token) return;
    const myReq = (minReqRef.current[serviceId] ?? 0) + 1;
    minReqRef.current[serviceId] = myReq;
    patch<Service>(
      `/api/v1/sellers/me/services/${serviceId}`,
      { min_order_value: value },
      token,
    )
      .then((updated) => {
        // Drop stale responses that resolve after a newer edit to this service.
        if (minReqRef.current[serviceId] !== myReq) return;
        setServices((prev) =>
          prev.map((s) => (s.id === serviceId ? updated : s)),
        );
      })
      .catch(() => {
        if (minReqRef.current[serviceId] !== myReq) return;
        setError("Could not save minimum order value.");
      });
  };

  const updateMin = (serviceId: number, raw: number) => {
    const value = Number.isFinite(raw) ? Math.max(0, Math.min(100000, raw)) : 0;
    setServices((prev) =>
      prev.map((s) => (s.id === serviceId ? { ...s, min_order_value: value } : s)),
    );
    if (minDebounceRef.current[serviceId]) {
      window.clearTimeout(minDebounceRef.current[serviceId]);
    }
    minDebounceRef.current[serviceId] = window.setTimeout(
      () => persistMin(serviceId, value),
      400,
    );
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

      {services.length > 0 && (
        <section className={styles.card}>
          <header className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Minimum order value</h2>
            <p className={styles.cardCaption}>
              Orders below this amount can&apos;t be placed for that service. Set
              to 0 for no minimum.
            </p>
          </header>
          {services.map((svc) => (
            <div key={svc.id} className={styles.serviceRow}>
              <span className={styles.serviceLabel}>{svc.name}</span>
              <span className={styles.unit}>₹</span>
              <input
                type="number"
                className={styles.radiusInput}
                min={0}
                max={100000}
                step={10}
                value={svc.min_order_value ?? 0}
                onChange={(e) => updateMin(svc.id, parseFloat(e.target.value))}
                aria-label={`Minimum order value for ${svc.name}`}
              />
            </div>
          ))}
        </section>
      )}

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
