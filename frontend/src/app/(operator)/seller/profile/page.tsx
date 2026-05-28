"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { get, patch } from "@/lib/api";
import { formatAddress } from "@/lib/format-address";
import { serviceGlyph } from "@/lib/serviceGlyph";
import type { SellerProfile, Service, Store } from "@/types";
import ProfileSectionCard from "@/components/ProfileSectionCard";
import VerificationBadge, {
  type VerificationBadgeStatus,
} from "@/components/VerificationBadge";
import styles from "./page.module.css";

const RESUBMIT_HREF = "/seller/signup?resubmit=true";

const MIN_KM = 0.5;
const MAX_KM = 50;
const STEP_KM = 0.5;

function clamp(km: number): number {
  const rounded = Math.round(km / STEP_KM) * STEP_KM;
  return Math.max(MIN_KM, Math.min(MAX_KM, rounded));
}

function maskAccountNumber(n: string | null | undefined): string | null {
  if (!n) return null;
  const last4 = n.slice(-4);
  if (last4.length < 4) return null;
  return `•••• •••• ${last4}`;
}

function toBadgeStatus(s: string): VerificationBadgeStatus {
  if (s === "approved") return "approved";
  if (s === "rejected") return "rejected";
  return "pending";
}

export default function SellerProfilePage() {
  const t = useTranslations("Seller.profile");
  const tc = useTranslations("Seller.common");
  const { token, dbUser, loading: authLoading } = useAuth();
  const [profile, setProfile] = useState<SellerProfile | null>(null);
  const [store, setStore] = useState<Store | null>(null);
  const [fetching, setFetching] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savingRadius, setSavingRadius] = useState(false);
  const debounceRef = useRef<number | null>(null);
  // Monotonic request id — drop stale PATCH responses that resolve after a newer one.
  const reqIdRef = useRef(0);
  const minReqRef = useRef<Record<number, number>>({});
  const minDebounceRef = useRef<Record<number, number>>({});

  useEffect(() => {
    if (authLoading || !dbUser || !token) return;
    let cancelled = false;
    Promise.all([
      get<SellerProfile>("/api/v1/sellers/me/profile", token),
      get<Store[]>("/api/v1/stores/my", token),
    ])
      .then(([p, stores]) => {
        if (cancelled) return;
        setProfile(p);
        setStore(stores[0] ?? null);
      })
      .catch(() => {
        if (!cancelled) setLoadError(t("loadError"));
      })
      .finally(() => {
        if (!cancelled) setFetching(false);
      });
    return () => {
      cancelled = true;
    };
  }, [authLoading, dbUser, token, t]);

  const tSettings = useTranslations("Seller.settings");

  const persistRadius = (km: number) => {
    if (!store || !token) return;
    const myReq = ++reqIdRef.current;
    setSavingRadius(true);
    setSaveError(null);
    patch<Store>(`/api/v1/stores/${store.id}`, { delivery_radius_km: km }, token)
      .then((updated) => {
        if (myReq === reqIdRef.current) setStore(updated);
      })
      .catch(() => {
        if (myReq === reqIdRef.current) setSaveError(tSettings("saveRadiusError"));
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
    setSaveError(null);
    patch<Service>(
      `/api/v1/sellers/me/services/${serviceId}`,
      { min_order_value: value },
      token,
    )
      .then((updated) => {
        // Drop stale responses that resolve after a newer edit to this service.
        if (minReqRef.current[serviceId] !== myReq) return;
        setProfile((prev) =>
          prev
            ? {
                ...prev,
                services: prev.services.map((s) =>
                  s.id === serviceId ? updated : s,
                ),
              }
            : prev,
        );
      })
      .catch(() => {
        if (minReqRef.current[serviceId] !== myReq) return;
        setSaveError(tSettings("saveMinOrderError"));
      });
  };

  const updateMin = (serviceId: number, raw: number) => {
    const value = Number.isFinite(raw) ? Math.max(0, Math.min(100000, raw)) : 0;
    setProfile((prev) =>
      prev
        ? {
            ...prev,
            services: prev.services.map((s) =>
              s.id === serviceId ? { ...s, min_order_value: value } : s,
            ),
          }
        : prev,
    );
    if (minDebounceRef.current[serviceId]) {
      window.clearTimeout(minDebounceRef.current[serviceId]);
    }
    minDebounceRef.current[serviceId] = window.setTimeout(
      () => persistMin(serviceId, value),
      400,
    );
  };

  const maskedAccount = useMemo(
    () => maskAccountNumber(profile?.bank_account_number),
    [profile?.bank_account_number],
  );

  if (authLoading || fetching) {
    return <div className={styles.loader}>{tc("loading")}</div>;
  }

  if (loadError || !profile) {
    return (
      <div className={styles.page}>
        <h1 className={styles.title}>{t("heading")}</h1>
        <div className={styles.errorBanner}>
          {loadError ?? t("loadError")}
        </div>
      </div>
    );
  }

  const storeName = store?.name ?? profile.business_name;
  const normalize = (s: string) => s.trim().toLocaleLowerCase();
  const showBusinessName =
    normalize(profile.business_name) !== normalize(storeName);
  const coverage = store
    ? Math.round(Math.PI * store.delivery_radius_km ** 2)
    : 0;

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>{t("heading")}</h1>

      {saveError && <div className={styles.errorBanner}>{saveError}</div>}

      <ProfileSectionCard
        title={t("sectionIdentity")}
        editHref={RESUBMIT_HREF}
        editLabel={t("editProfile")}
      >
        <div className={styles.identityRow}>
          <div className={styles.avatar} aria-hidden>
            {storeName.charAt(0).toUpperCase() || "?"}
          </div>
          <div className={styles.identityText}>
            <div className={styles.storeName}>{storeName}</div>
            <div className={styles.kvRow}>
              <span className={styles.kvLabel}>{t("ownerLabel")}:</span>
              <span>{profile.full_name}</span>
            </div>
            <div className={styles.kvRow}>
              <span className={styles.kvLabel}>{t("phoneLabel")}:</span>
              <span>{profile.phone}</span>
            </div>
            {showBusinessName && (
              <div className={styles.kvRow}>
                <span className={styles.kvLabel}>{t("businessNameLabel")}:</span>
                <span>{profile.business_name}</span>
              </div>
            )}
          </div>
        </div>
        <VerificationBadge
          status={toBadgeStatus(profile.verification_status)}
          reason={profile.rejection_reason}
        />
      </ProfileSectionCard>

      <ProfileSectionCard
        title={t("sectionAddress")}
        editHref={RESUBMIT_HREF}
        editLabel={t("editProfile")}
      >
        <div className={styles.addressText}>{formatAddress(profile.address)}</div>
        <div
          className={`${styles.pinRow} ${
            store?.pin_confirmed ? styles.pinConfirmed : styles.pinPending
          }`}
        >
          <span aria-hidden>📍</span>
          <span>
            {store?.pin_confirmed ? t("pinConfirmed") : t("pinNotConfirmed")}
          </span>
        </div>
      </ProfileSectionCard>

      <ProfileSectionCard
        title={t("sectionLegal")}
        editHref={RESUBMIT_HREF}
        editLabel={t("editProfile")}
      >
        <div className={styles.kvRow}>
          <span className={styles.kvLabel}>{t("gstLabel")}:</span>
          <span>{profile.gst_number ?? t("notAdded")}</span>
        </div>
        <div className={styles.kvRow}>
          <span className={styles.kvLabel}>{t("fssaiLabel")}:</span>
          <span>{profile.fssai_license ?? t("notAdded")}</span>
        </div>
      </ProfileSectionCard>

      <ProfileSectionCard
        title={t("sectionBanking")}
        editHref={RESUBMIT_HREF}
        editLabel={t("editProfile")}
      >
        <div className={styles.kvRow}>
          <span className={styles.kvLabel}>{t("accountLabel")}:</span>
          <span className={styles.mono}>{maskedAccount ?? t("notAdded")}</span>
        </div>
        <div className={styles.kvRow}>
          <span className={styles.kvLabel}>{t("ifscLabel")}:</span>
          <span className={styles.mono}>{profile.bank_ifsc ?? t("notAdded")}</span>
        </div>
      </ProfileSectionCard>

      <ProfileSectionCard
        title={t("sectionServices")}
        editHref={RESUBMIT_HREF}
        editLabel={t("editProfile")}
      >
        {profile.services.length === 0 ? (
          <div className={styles.servicesEmpty}>{t("servicesEmpty")}</div>
        ) : (
          <div className={styles.serviceChips}>
            {profile.services.map((svc) => (
              <span key={svc.id} className={styles.serviceChip}>
                <span aria-hidden>{serviceGlyph(svc.slug)}</span>
                <span>{svc.name}</span>
              </span>
            ))}
          </div>
        )}
      </ProfileSectionCard>

      {store && (
        <ProfileSectionCard title={tSettings("deliveryRadius")}>
          <p className={styles.cardCaption}>
            {tSettings.rich("radiusCaption", {
              coverage,
              strong: (chunks) => <strong>{chunks}</strong>,
            })}
          </p>
          <div className={styles.radiusRow}>
            <button
              type="button"
              className={styles.stepBtn}
              onClick={() => bump(-STEP_KM)}
              aria-label={tSettings("decreaseRadius")}
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
              aria-label={tSettings("radiusInputLabel")}
            />
            <span className={styles.unit}>km</span>
            <button
              type="button"
              className={styles.stepBtn}
              onClick={() => bump(STEP_KM)}
              aria-label={tSettings("increaseRadius")}
              disabled={store.delivery_radius_km >= MAX_KM}
            >
              +
            </button>
            {savingRadius && (
              <span className={styles.savingChip}>{tc("saving")}</span>
            )}
          </div>
        </ProfileSectionCard>
      )}

      {profile.services.length > 0 && (
        <ProfileSectionCard title={tSettings("minOrderValue")}>
          <p className={styles.cardCaption}>{tSettings("minOrderCaption")}</p>
          {profile.services.map((svc) => (
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
                aria-label={tSettings("minOrderInputLabel", {
                  service: svc.name,
                })}
              />
            </div>
          ))}
        </ProfileSectionCard>
      )}

      {store && (
        <Link
          href={`/stores/${store.id}`}
          target="_blank"
          rel="noopener noreferrer"
          className={styles.storefrontLink}
        >
          {t("viewStorefront")}
        </Link>
      )}
    </div>
  );
}
