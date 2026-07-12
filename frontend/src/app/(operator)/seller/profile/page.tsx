"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { get, patch } from "@/lib/api";
import { formatAddress } from "@/lib/format-address";
import { serviceGlyph } from "@/lib/serviceGlyph";
import { profileEditErrorMessage } from "@/lib/sellerProfileValidation";
import type {
  SellerProfile,
  SellerProfileChangeGroup,
  SellerProfileChangeRequest,
  Service,
  Store,
} from "@/types";
import ProfileSectionCard from "@/components/ProfileSectionCard";
import Avatar from "@/components/Avatar";
import AvatarUploader from "@/components/AvatarUploader";
import { uploadSellerAvatar } from "@/lib/avatars";
import ProfileChangeRequestModal from "@/components/ProfileChangeRequestModal";
import VerificationBadge, {
  type VerificationBadgeStatus,
} from "@/components/VerificationBadge";
import {
  createMyChangeRequest,
  listMyChangeRequests,
} from "@/lib/changeRequests";
import styles from "./page.module.css";

const RESUBMIT_HREF = "/seller/signup?resubmit=true";

/** Build the current values dict for a given group, matching the per-group
 *  payload schema expected by `ProfileChangeRequestModal`. Returns null for
 *  groups whose backing data is missing (e.g. store_basics with no store). */
function buildCurrentValues(
  group: SellerProfileChangeGroup,
  profile: SellerProfile,
  store: Store | null,
): Record<string, unknown> | null {
  switch (group) {
    case "identity":
      return {
        full_name: profile.full_name,
        business_name: profile.business_name,
        phone: profile.phone,
      };
    case "address":
      return {
        address_line1: profile.address.address_line1,
        address_line2: profile.address.address_line2 ?? "",
        landmark: profile.address.landmark ?? "",
        city: profile.address.city,
        state: profile.address.state,
        pincode: profile.address.pincode,
        country: profile.address.country,
        latitude: profile.address.latitude ?? "",
        longitude: profile.address.longitude ?? "",
      };
    case "legal":
      return {
        gst_number: profile.gst_number ?? "",
        fssai_license: profile.fssai_license ?? "",
      };
    case "banking":
      return {
        bank_account_number: profile.bank_account_number ?? "",
        bank_ifsc: profile.bank_ifsc ?? "",
      };
    case "store_basics":
      if (!store) return null;
      return {
        delivery_radius_km: store.delivery_radius_km,
      };
    case "services":
      return {
        services: profile.services.map((s) => ({
          service_id: s.id,
          name: s.name,
          free_delivery_threshold: s.free_delivery_threshold ?? 0,
          delivery_fee: s.delivery_fee ?? 0,
          delivery_eta_min_minutes: s.delivery_eta_min_minutes ?? 30,
          delivery_eta_max_minutes: s.delivery_eta_max_minutes ?? 60,
          pickup_enabled: s.pickup_enabled ?? false,
        })),
      };
    default:
      return null;
  }
}

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
  const tCR = useTranslations("Seller.changeRequests");
  const { token, dbUser, loading: authLoading } = useAuth();
  const [profile, setProfile] = useState<SellerProfile | null>(null);
  const [store, setStore] = useState<Store | null>(null);
  const [openCRs, setOpenCRs] = useState<SellerProfileChangeRequest[]>([]);
  const [fetching, setFetching] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savingRadius, setSavingRadius] = useState(false);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [avatarNotice, setAvatarNotice] = useState<string | null>(null);
  const [editingGroup, setEditingGroup] =
    useState<SellerProfileChangeGroup | null>(null);
  const debounceRef = useRef<number | null>(null);
  // Monotonic request id — drop stale PATCH responses that resolve after a newer one.
  const reqIdRef = useRef(0);
  const minReqRef = useRef<Record<number, number>>({});
  const minDebounceRef = useRef<Record<number, number>>({});
  // Mirrors `profile` so the debounced persist reads the freshest service
  // values without re-subscribing the timeout to state changes.
  const profileRef = useRef<SellerProfile | null>(null);
  useEffect(() => {
    profileRef.current = profile;
  }, [profile]);

  useEffect(() => {
    if (authLoading || !dbUser || !token) return;
    let cancelled = false;
    Promise.all([
      get<SellerProfile>("/api/v1/sellers/me/profile", token),
      get<Store[]>("/api/v1/stores/my", token),
      listMyChangeRequests(token, "open").catch(() => [] as SellerProfileChangeRequest[]),
    ])
      .then(([p, stores, crs]) => {
        if (cancelled) return;
        setProfile(p);
        setStore(stores[0] ?? null);
        setOpenCRs(crs);
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

  const openCRsByGroup = useMemo(() => {
    const map: Partial<Record<SellerProfileChangeGroup, SellerProfileChangeRequest>> =
      {};
    for (const cr of openCRs) {
      map[cr.group] = cr;
    }
    return map;
  }, [openCRs]);

  async function refreshOpenCRs() {
    if (!token) return;
    try {
      const fresh = await listMyChangeRequests(token, "open");
      setOpenCRs(fresh);
    } catch {
      // best-effort refresh; leave existing state
    }
  }

  const onUploadSellerAvatar = async (blob: Blob) => {
    if (!token) return;
    setAvatarBusy(true);
    setAvatarNotice(null);
    setSaveError(null);
    try {
      await uploadSellerAvatar(blob, token);
      setAvatarNotice(t("avatarSubmitted"));
      await refreshOpenCRs();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : t("avatarUploadFailed"));
    } finally {
      setAvatarBusy(false);
    }
  };

  const onRemoveSellerAvatar = async () => {
    if (!token) return;
    setAvatarBusy(true);
    setAvatarNotice(null);
    setSaveError(null);
    try {
      await createMyChangeRequest(token, { group: "avatar", proposed: { avatar_url: "" } });
      setAvatarNotice(t("avatarRemovalSubmitted"));
      await refreshOpenCRs();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : t("avatarRemovalFailed"));
    } finally {
      setAvatarBusy(false);
    }
  };

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
      .catch((err) => {
        if (myReq === reqIdRef.current)
          setSaveError(profileEditErrorMessage(err, tSettings("saveRadiusError")));
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

  const persistService = (
    serviceId: number,
    body: {
      free_delivery_threshold: number;
      delivery_fee: number;
      delivery_eta_min_minutes: number;
      delivery_eta_max_minutes: number;
      pickup_enabled: boolean;
    },
  ) => {
    if (!token) return;
    const myReq = (minReqRef.current[serviceId] ?? 0) + 1;
    minReqRef.current[serviceId] = myReq;
    setSaveError(null);
    patch<Service>(
      `/api/v1/sellers/me/services/${serviceId}`,
      body,
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
      .catch((err) => {
        if (minReqRef.current[serviceId] !== myReq) return;
        setSaveError(profileEditErrorMessage(err, tSettings("saveMinOrderError")));
      });
  };

  const schedulePersist = (serviceId: number) => {
    if (minDebounceRef.current[serviceId]) {
      window.clearTimeout(minDebounceRef.current[serviceId]);
    }
    minDebounceRef.current[serviceId] = window.setTimeout(() => {
      // Read the freshest values off the ref at fire time so concurrent edits
      // to min / eta on the same row are persisted together.
      const svc = profileRef.current?.services.find((s) => s.id === serviceId);
      if (svc) {
        const etaMin = svc.delivery_eta_min_minutes ?? 30;
        const etaMax = svc.delivery_eta_max_minutes ?? 60;
        if (etaMin > etaMax) {
          setSaveError(t("etaOrderError"));
          return;
        }
        persistService(serviceId, {
          free_delivery_threshold: svc.free_delivery_threshold ?? 0,
          delivery_fee: svc.delivery_fee ?? 0,
          delivery_eta_min_minutes: etaMin,
          delivery_eta_max_minutes: etaMax,
          pickup_enabled: svc.pickup_enabled ?? false,
        });
      }
    }, 400);
  };

  const updateThreshold = (serviceId: number, raw: number) => {
    const value = Number.isFinite(raw) ? Math.max(0, Math.min(100000, raw)) : 0;
    setProfile((prev) =>
      prev
        ? {
            ...prev,
            services: prev.services.map((s) =>
              s.id === serviceId ? { ...s, free_delivery_threshold: value } : s,
            ),
          }
        : prev,
    );
    schedulePersist(serviceId);
  };

  const updateFee = (serviceId: number, raw: number) => {
    const value = Number.isFinite(raw) ? Math.max(0, Math.min(5000, raw)) : 0;
    setProfile((prev) =>
      prev
        ? {
            ...prev,
            services: prev.services.map((s) =>
              s.id === serviceId ? { ...s, delivery_fee: value } : s,
            ),
          }
        : prev,
    );
    schedulePersist(serviceId);
  };

  const updatePickup = (serviceId: number, value: boolean) => {
    setProfile((prev) =>
      prev
        ? {
            ...prev,
            services: prev.services.map((s) =>
              s.id === serviceId ? { ...s, pickup_enabled: value } : s,
            ),
          }
        : prev,
    );
    schedulePersist(serviceId);
  };

  const updateEta = (serviceId: number, field: "min" | "max", raw: number) => {
    const value = Number.isFinite(raw) ? Math.max(1, Math.min(20160, raw)) : 1;
    setProfile((prev) =>
      prev
        ? {
            ...prev,
            services: prev.services.map((s) =>
              s.id === serviceId
                ? {
                    ...s,
                    delivery_eta_min_minutes:
                      field === "min" ? value : s.delivery_eta_min_minutes,
                    delivery_eta_max_minutes:
                      field === "max" ? value : s.delivery_eta_max_minutes,
                  }
                : s,
            ),
          }
        : prev,
    );
    schedulePersist(serviceId);
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
  const isApproved = profile.verification_status === "approved";

  /** For a CR-aware card: return the right `action` slot + an optional inline
   *  banner. Approved sellers with no open CR get an Edit button that opens
   *  the modal. Approved sellers with an open CR get a banner + View link,
   *  and no edit affordance. Non-approved sellers fall back to the legacy
   *  resubmit link (handled by the caller passing `editHref` instead). */
  const cardCRChrome = (group: SellerProfileChangeGroup) => {
    const openCR = openCRsByGroup[group];
    if (!isApproved) return { action: undefined, banner: null };
    if (openCR) {
      const isChanges = openCR.status === "changes_requested";
      return {
        action: null,
        banner: (
          <div
            className={`${styles.crBanner} ${
              isChanges ? styles.crBannerWarn : styles.crBannerInfo
            }`}
          >
            <span>
              {isChanges
                ? tCR("changesRequestedBanner")
                : tCR("submittedBanner")}
            </span>
            <Link
              href={`/seller/profile/requests/${openCR.id}`}
              className={styles.crBannerLink}
            >
              {tCR("viewRequest")}
            </Link>
          </div>
        ),
      };
    }
    return {
      action: (
        <button
          type="button"
          className={styles.editBtn}
          onClick={() => setEditingGroup(group)}
        >
          {tc("edit")}
        </button>
      ),
      banner: null,
    };
  };

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1 className={styles.title}>{t("heading")}</h1>
        {isApproved && (
          <Link
            href="/seller/profile/requests"
            className={styles.requestsLink}
          >
            {tCR("viewAll")}
          </Link>
        )}
      </div>

      {saveError && <div className={styles.errorBanner}>{saveError}</div>}

      <div className={styles.avatarSection}>
        <Avatar
          avatarUrl={profile.avatar_url}
          name={profile.full_name}
          seed={profile.phone}
          size={72}
        />
        <div>
          <AvatarUploader busy={avatarBusy} onUpload={onUploadSellerAvatar} />
          {profile.avatar_url && (
            <button
              type="button"
              className={styles.removeAvatar}
              onClick={onRemoveSellerAvatar}
              disabled={avatarBusy}
            >
              {t("removePicture")}
            </button>
          )}
          {avatarNotice && <p className={styles.avatarNotice}>{avatarNotice}</p>}
          <p className={styles.avatarHint}>{t("avatarHint")}</p>
        </div>
      </div>

      {(() => {
        const chrome = cardCRChrome("identity");
        return (
          <ProfileSectionCard
            title={t("sectionIdentity")}
            editHref={isApproved ? undefined : RESUBMIT_HREF}
            editLabel={t("editProfile")}
            action={chrome.action ?? undefined}
          >
            {chrome.banner}
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
                    <span className={styles.kvLabel}>
                      {t("businessNameLabel")}:
                    </span>
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
        );
      })()}

      {(() => {
        const chrome = cardCRChrome("address");
        return (
          <ProfileSectionCard
            title={t("sectionAddress")}
            editHref={isApproved ? undefined : RESUBMIT_HREF}
            editLabel={t("editProfile")}
            action={chrome.action ?? undefined}
          >
            {chrome.banner}
            <div className={styles.addressText}>
              {formatAddress(profile.address)}
            </div>
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
        );
      })()}

      {(() => {
        const chrome = cardCRChrome("legal");
        return (
          <ProfileSectionCard
            title={t("sectionLegal")}
            editHref={isApproved ? undefined : RESUBMIT_HREF}
            editLabel={t("editProfile")}
            action={chrome.action ?? undefined}
          >
            {chrome.banner}
            <div className={styles.kvRow}>
              <span className={styles.kvLabel}>{t("gstLabel")}:</span>
              <span>{profile.gst_number ?? t("notAdded")}</span>
            </div>
            <div className={styles.kvRow}>
              <span className={styles.kvLabel}>{t("fssaiLabel")}:</span>
              <span>{profile.fssai_license ?? t("notAdded")}</span>
            </div>
          </ProfileSectionCard>
        );
      })()}

      {(() => {
        const chrome = cardCRChrome("banking");
        return (
          <ProfileSectionCard
            title={t("sectionBanking")}
            editHref={isApproved ? undefined : RESUBMIT_HREF}
            editLabel={t("editProfile")}
            action={chrome.action ?? undefined}
          >
            {chrome.banner}
            <div className={styles.kvRow}>
              <span className={styles.kvLabel}>{t("accountLabel")}:</span>
              <span className={styles.mono}>
                {maskedAccount ?? t("notAdded")}
              </span>
            </div>
            <div className={styles.kvRow}>
              <span className={styles.kvLabel}>{t("ifscLabel")}:</span>
              <span className={styles.mono}>
                {profile.bank_ifsc ?? t("notAdded")}
              </span>
            </div>
          </ProfileSectionCard>
        );
      })()}

      {(() => {
        const chrome = cardCRChrome("services");
        return (
          <ProfileSectionCard
            title={t("sectionServices")}
            editHref={isApproved ? undefined : RESUBMIT_HREF}
            editLabel={t("editProfile")}
            action={chrome.action ?? undefined}
          >
            {chrome.banner}
            {profile.services.length === 0 ? (
              <div className={styles.servicesEmpty}>{t("servicesEmpty")}</div>
            ) : (
              <>
                <p className={styles.cardCaption}>
                  {tSettings("minOrderCaption")}
                </p>
                {profile.services.map((svc) => (
                  <div key={svc.id} className={styles.serviceRow}>
                    <span className={styles.serviceLabel}>
                      <span aria-hidden>{serviceGlyph(svc.slug)}</span>{" "}
                      {svc.name}
                    </span>
                    <span className={styles.unit}>₹</span>
                    <input
                      type="number"
                      className={styles.radiusInput}
                      min={0}
                      max={100000}
                      step={10}
                      value={svc.free_delivery_threshold ?? 0}
                      onChange={(e) =>
                        updateThreshold(svc.id, parseFloat(e.target.value))
                      }
                      aria-label={tSettings("freeDeliveryThresholdInputLabel", {
                        service: svc.name,
                      })}
                      readOnly={isApproved}
                      disabled={isApproved}
                    />
                    <span className={styles.unit}>{t("feeUnit")}</span>
                    <input
                      type="number"
                      className={styles.radiusInput}
                      min={0}
                      max={5000}
                      step={5}
                      value={svc.delivery_fee ?? 0}
                      onChange={(e) =>
                        updateFee(svc.id, parseFloat(e.target.value))
                      }
                      aria-label={tSettings("deliveryFeeInputLabel", {
                        service: svc.name,
                      })}
                      readOnly={isApproved}
                      disabled={isApproved}
                    />
                    <span className={styles.unit}>{t("etaUnit")}</span>
                    <input
                      type="number"
                      className={styles.radiusInput}
                      min={1}
                      max={20160}
                      step={5}
                      value={svc.delivery_eta_min_minutes ?? 30}
                      onChange={(e) =>
                        updateEta(svc.id, "min", parseFloat(e.target.value))
                      }
                      aria-label={t("etaMinAria", { name: svc.name })}
                      readOnly={isApproved}
                      disabled={isApproved}
                    />
                    <span className={styles.unit}>–</span>
                    <input
                      type="number"
                      className={styles.radiusInput}
                      min={1}
                      max={20160}
                      step={5}
                      value={svc.delivery_eta_max_minutes ?? 60}
                      onChange={(e) =>
                        updateEta(svc.id, "max", parseFloat(e.target.value))
                      }
                      aria-label={t("etaMaxAria", { name: svc.name })}
                      readOnly={isApproved}
                      disabled={isApproved}
                    />
                    <span className={styles.unit}>{t("minUnit")}</span>
                    <label className={styles.pickupToggle}>
                      <input
                        type="checkbox"
                        checked={svc.pickup_enabled ?? false}
                        onChange={(e) => updatePickup(svc.id, e.target.checked)}
                        disabled={isApproved}
                      />
                      {tSettings("allowPickup")}
                    </label>
                  </div>
                ))}
              </>
            )}
          </ProfileSectionCard>
        );
      })()}

      {store &&
        (() => {
          const chrome = cardCRChrome("store_basics");
          // Approved sellers must use the change-request modal — direct PATCH
          // of name/delivery_radius_km is 409'd server-side. Non-approved
          // sellers (rare here; the dashboard is gated) keep the inline
          // edit since no CR system applies pre-approval.
          const radiusEditDisabled = isApproved;
          return (
            <ProfileSectionCard
              title={tSettings("deliveryRadius")}
              action={chrome.action ?? undefined}
            >
              {chrome.banner}
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
                  disabled={
                    radiusEditDisabled || store.delivery_radius_km <= MIN_KM
                  }
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
                  readOnly={radiusEditDisabled}
                  disabled={radiusEditDisabled}
                />
                <span className={styles.unit}>km</span>
                <button
                  type="button"
                  className={styles.stepBtn}
                  onClick={() => bump(STEP_KM)}
                  aria-label={tSettings("increaseRadius")}
                  disabled={
                    radiusEditDisabled || store.delivery_radius_km >= MAX_KM
                  }
                >
                  +
                </button>
                {savingRadius && (
                  <span className={styles.savingChip}>{tc("saving")}</span>
                )}
              </div>
            </ProfileSectionCard>
          );
        })()}

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

      {editingGroup &&
        (() => {
          const current = buildCurrentValues(editingGroup, profile, store);
          // Defensive: if backing data is missing (e.g. store_basics with no
          // store), simply omit the modal — closing the editing state happens
          // in an effect below to avoid setState during render.
          if (!current) return null;
          return (
            <ProfileChangeRequestModal
              group={editingGroup}
              currentValues={current}
              open
              onClose={() => setEditingGroup(null)}
              onSubmit={async (proposed, note, phoneChangeToken) => {
                if (!token) return;
                await createMyChangeRequest(token, {
                  group: editingGroup,
                  proposed,
                  note,
                  phone_change_token: phoneChangeToken,
                });
                await refreshOpenCRs();
              }}
            />
          );
        })()}
    </div>
  );
}
