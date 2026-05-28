"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import { formatAddress } from "@/lib/format-address";
import { serviceGlyph } from "@/lib/serviceGlyph";
import type { SellerProfile, Store } from "@/types";
import ProfileSectionCard from "@/components/ProfileSectionCard";
import VerificationBadge, {
  type VerificationBadgeStatus,
} from "@/components/VerificationBadge";
import styles from "./page.module.css";

const RESUBMIT_HREF = "/seller/signup?resubmit=true";

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
  const [error, setError] = useState<string | null>(null);

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
        if (!cancelled) setError(t("loadError"));
      })
      .finally(() => {
        if (!cancelled) setFetching(false);
      });
    return () => {
      cancelled = true;
    };
  }, [authLoading, dbUser, token, t]);

  const maskedAccount = useMemo(
    () => maskAccountNumber(profile?.bank_account_number),
    [profile?.bank_account_number],
  );

  if (authLoading || fetching) {
    return <div className={styles.loader}>{tc("loading")}</div>;
  }

  if (error || !profile) {
    return (
      <div className={styles.page}>
        <h1 className={styles.title}>{t("heading")}</h1>
        <div className={styles.errorBanner}>
          {error ?? t("loadError")}
        </div>
      </div>
    );
  }

  const storeName = store?.name ?? profile.business_name;
  const normalize = (s: string) => s.trim().toLocaleLowerCase();
  const showBusinessName =
    normalize(profile.business_name) !== normalize(storeName);

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>{t("heading")}</h1>

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
