"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import PhoneVerifyModal from "@/components/PhoneVerifyModal";
import Avatar from "@/components/Avatar";
import AvatarUploader from "@/components/AvatarUploader";
import { get, patch } from "@/lib/api";
import { deleteCustomerAvatar, uploadCustomerAvatar } from "@/lib/avatars";
import { getCustomerStats } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import { apiErrorKey } from "@/lib/errors";
import type { CustomerProfile, CustomerStats } from "@/types";
import styles from "./page.module.css";

interface ProfileForm {
  first_name: string;
  last_name: string;
  date_of_birth: string;
}

interface ProfileErrors {
  first_name?: string;
}

interface FastApiValidationIssue {
  loc?: Array<string | number>;
  msg?: string;
}

function formatIndianPhone(phone: string | null | undefined): string | null {
  if (!phone) return null;
  const digits = phone.replace(/\D/g, "").replace(/^91/, "").slice(-10);
  if (digits.length !== 10) return phone;
  return `+91 ${digits.slice(0, 5)} ${digits.slice(5)}`;
}

function profileFormFrom(profile: CustomerProfile): ProfileForm {
  return {
    first_name: profile.first_name,
    last_name: profile.last_name ?? "",
    date_of_birth: profile.date_of_birth ?? "",
  };
}

function apiErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as FastApiValidationIssue;
    if (typeof first.msg === "string") return first.msg;
  }
  if (error instanceof Error) return error.message;
  return fallback;
}

function normalizeOptional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export default function AccountProfilePage() {
  const { token, setAvatarUrl } = useAuth();
  const t = useTranslations("Account.profile");
  const tErr = useTranslations("Errors");

  const localizedError = useCallback(
    (error: unknown, fallback: string): string => {
      const key = apiErrorKey(error);
      if (key) return tErr(key.replace(/^Errors\./, ""));
      return apiErrorMessage(error, fallback);
    },
    [tErr],
  );

  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [stats, setStats] = useState<CustomerStats | null>(null);
  const [mode, setMode] = useState<"view" | "edit">("view");
  const [profileForm, setProfileForm] = useState<ProfileForm>({
    first_name: "",
    last_name: "",
    date_of_birth: "",
  });
  const [snapshot, setSnapshot] = useState<ProfileForm | null>(null);
  const [profileErrors, setProfileErrors] = useState<ProfileErrors>({});
  const [sectionError, setSectionError] = useState<string | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [phoneModal, setPhoneModal] = useState<
    { open: false } | { open: true; initialStep: "confirm" | "edit" }
  >({ open: false });

  useEffect(() => {
    if (!saveSuccess) return;
    const handle = window.setTimeout(() => setSaveSuccess(false), 4000);
    return () => window.clearTimeout(handle);
  }, [saveSuccess]);

  useEffect(() => {
    if (!token) {
      setLoadingProfile(false);
      setSectionError(t("loadError"));
      return;
    }
    let active = true;
    setLoadingProfile(true);
    Promise.all([
      get<CustomerProfile>("/api/v1/customers/me", token),
      getCustomerStats(token).catch(() => null),
    ])
      .then(([data, s]) => {
        if (!active) return;
        setProfile(data);
        setProfileForm(profileFormFrom(data));
        setStats(s);
      })
      .catch((error) => {
        if (!active) return;
        setSectionError(localizedError(error, t("loadError")));
      })
      .finally(() => {
        if (active) setLoadingProfile(false);
      });
    return () => {
      active = false;
    };
  }, [token, t, localizedError]);

  const onUploadAvatar = async (blob: Blob) => {
    if (!token) return;
    setAvatarBusy(true);
    try {
      const next = await uploadCustomerAvatar(blob, token);
      setProfile(next);
      setAvatarUrl(next.avatar_url); // update navbar + sidebar immediately
    } catch (error) {
      setSectionError(localizedError(error, t("saveProfileError")));
    } finally {
      setAvatarBusy(false);
    }
  };

  const onRemoveAvatar = async () => {
    if (!token) return;
    setAvatarBusy(true);
    try {
      const next = await deleteCustomerAvatar(token);
      setProfile(next);
      setAvatarUrl(next.avatar_url);
    } catch (error) {
      setSectionError(localizedError(error, t("saveProfileError")));
    } finally {
      setAvatarBusy(false);
    }
  };

  const validateProfile = (): ProfileErrors => {
    const errors: ProfileErrors = {};
    if (!profileForm.first_name.trim()) {
      errors.first_name = t("firstNameRequired");
    }
    return errors;
  };

  const saveProfile = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token) return;
    setSectionError(null);
    const errors = validateProfile();
    setProfileErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSavingProfile(true);
    try {
      const next = await patch<CustomerProfile>(
        "/api/v1/customers/me",
        {
          first_name: profileForm.first_name.trim(),
          last_name: normalizeOptional(profileForm.last_name),
          date_of_birth: normalizeOptional(profileForm.date_of_birth),
        },
        token,
      );
      setProfile(next);
      setProfileForm(profileFormFrom(next));
      setProfileErrors({});
      setSnapshot(null);
      setMode("view");
      setSaveSuccess(true);
    } catch (error) {
      setSectionError(localizedError(error, t("saveProfileError")));
    } finally {
      setSavingProfile(false);
    }
  };

  if (loadingProfile) {
    return <div className={styles.loading}>{t("loading")}</div>;
  }

  if (!profile) {
    return (
      <div className={styles.page}>
        <div className={styles.errorBanner}>{sectionError ?? t("loadError")}</div>
      </div>
    );
  }

  const phoneVerifiedAt = profile.phone_verified_at;

  return (
    <div className={styles.page}>
      {sectionError && <div className={styles.errorBanner}>{sectionError}</div>}
      {saveSuccess && (
        <div className={styles.successBanner} role="status" aria-live="polite">
          {t("saved")}
        </div>
      )}

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <h2 className={styles.sectionTitle}>{t("profileSection")}</h2>
            <p className={styles.sectionSubtitle}>{profile.email}</p>
          </div>
          {mode === "view" && (
            <button
              type="button"
              className="btn btn-outline"
              onClick={() => {
                setSaveSuccess(false);
                setSnapshot(profileForm);
                setProfileErrors({});
                setMode("edit");
              }}
            >
              {t("editButton")}
            </button>
          )}
        </div>

        <div className={styles.avatarRow}>
          <Avatar
            avatarUrl={profile.avatar_url}
            name={`${profile.first_name} ${profile.last_name ?? ""}`}
            seed={profile.email}
            size={64}
          />
          <div>
            <div className={styles.avatarLabel}>
              {profile.first_name} {profile.last_name ?? ""}
            </div>
            <div className={styles.avatarEmail}>{profile.email}</div>
            <AvatarUploader busy={avatarBusy} onUpload={onUploadAvatar} />
            {profile.avatar_url && (
              <button
                type="button"
                className={styles.removeAvatar}
                onClick={onRemoveAvatar}
                disabled={avatarBusy}
              >
                Remove picture
              </button>
            )}
          </div>
        </div>

        {mode === "view" ? (
          <div className={styles.viewGrid}>
            <div className={styles.viewField}>
              <span className={styles.viewLabel}>{t("firstNameLabel")}</span>
              <span className={styles.viewValue}>{profile.first_name || "—"}</span>
            </div>
            <div className={styles.viewField}>
              <span className={styles.viewLabel}>{t("lastNameLabel")}</span>
              <span className={styles.viewValue}>{profile.last_name || "—"}</span>
            </div>
            <div className={styles.viewField}>
              <span className={styles.viewLabel}>{t("dobLabel")}</span>
              <span className={styles.viewValue} suppressHydrationWarning>
                {profile.date_of_birth
                  ? new Date(profile.date_of_birth).toLocaleDateString()
                  : "—"}
              </span>
            </div>
            <div className={styles.viewField}>
              <span className={styles.viewLabel}>{t("emailLabel")}</span>
              <span className={styles.viewValue}>{profile.email}</span>
            </div>
          </div>
        ) : (
          <form className={styles.profileForm} onSubmit={saveProfile}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="first-name">
                {t("firstNameLabel")}
              </label>
              <input
                id="first-name"
                className={`${styles.input} ${profileErrors.first_name ? styles.inputError : ""}`}
                value={profileForm.first_name}
                onChange={(e) =>
                  setProfileForm((c) => ({ ...c, first_name: e.target.value }))
                }
                maxLength={80}
                required
                autoFocus
              />
              {profileErrors.first_name && (
                <span className={styles.errorText}>{profileErrors.first_name}</span>
              )}
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="last-name">
                {t("lastNameLabel")}
              </label>
              <input
                id="last-name"
                className={styles.input}
                value={profileForm.last_name}
                onChange={(e) =>
                  setProfileForm((c) => ({ ...c, last_name: e.target.value }))
                }
                maxLength={80}
              />
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="dob">
                {t("dobLabel")}
              </label>
              <input
                id="dob"
                type="date"
                className={styles.input}
                value={profileForm.date_of_birth}
                max={new Date().toISOString().slice(0, 10)}
                onChange={(e) =>
                  setProfileForm((c) => ({ ...c, date_of_birth: e.target.value }))
                }
              />
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="email">
                {t("emailLabel")}
              </label>
              <input id="email" className={styles.input} value={profile.email} readOnly disabled />
            </div>

            <div className={styles.formActions}>
              <button className="btn btn-primary" type="submit" disabled={savingProfile}>
                {savingProfile ? t("saving") : t("saveProfile")}
              </button>
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => {
                  if (snapshot) setProfileForm(snapshot);
                  setProfileErrors({});
                  setSectionError(null);
                  setMode("view");
                }}
                disabled={savingProfile}
              >
                {t("cancelButton")}
              </button>
            </div>
          </form>
        )}
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <h2 className={styles.sectionTitle}>{t("phoneSection")}</h2>
          </div>
        </div>
        <div className={styles.phoneCard}>
          <div className={styles.phoneInfo}>
            <span className={styles.phoneNumber}>
              {formatIndianPhone(profile.phone) ?? t("phoneNotSet")}
            </span>
            {profile.phone && (
              <span
                className={
                  profile.phone_verified_at
                    ? styles.phoneBadgeVerified
                    : styles.phoneBadgeUnverified
                }
              >
                <span aria-hidden="true">
                  {profile.phone_verified_at ? "✓" : "⚠"}
                </span>
                {" "}
                {profile.phone_verified_at
                  ? t("phoneStatusVerified")
                  : t("phoneStatusUnverified")}
              </span>
            )}
          </div>
          <button
            type="button"
            className="btn btn-outline"
            onClick={() => {
              const step =
                profile.phone && !profile.phone_verified_at ? "confirm" : "edit";
              setPhoneModal({ open: true, initialStep: step });
            }}
          >
            {!profile.phone
              ? t("btnAddNumber")
              : profile.phone_verified_at
                ? t("btnChangeNumber")
                : t("verifyPhone")}
          </button>
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <h2 className={styles.sectionTitle}>{t("statsTitle")}</h2>
            <p className={styles.sectionSubtitle}>{t("statsSubtitle")}</p>
          </div>
        </div>
        <div className={styles.statsCard}>
          <div className={styles.statItem}>
            <span className={styles.statLabel}>{t("ordersThisMonth")}</span>
            <span className={styles.statValue}>{stats?.orders_this_month ?? "—"}</span>
          </div>
          <div className={styles.statItem}>
            <span className={styles.statLabel}>{t("lifetimeSpend")}</span>
            <span className={styles.statValue}>
              {stats ? `₹${stats.lifetime_spend.toFixed(0)}` : "—"}
            </span>
          </div>
          <div className={styles.statItem}>
            <span className={styles.statLabel}>{t("mostOrderedStore")}</span>
            <span className={styles.statValue}>
              {stats?.most_ordered_store_name ?? "—"}
            </span>
          </div>
          {phoneVerifiedAt && (
            <div className={styles.statItem}>
              <span className={styles.statLabel}>{t("phoneVerifiedSince")}</span>
              <span className={styles.statValue} suppressHydrationWarning>
                {new Date(phoneVerifiedAt).toLocaleDateString()}
              </span>
            </div>
          )}
        </div>
      </section>

      {phoneModal.open && (
        <PhoneVerifyModal
          currentPhone={profile.phone ?? null}
          initialStep={phoneModal.initialStep}
          onClose={() => setPhoneModal({ open: false })}
          onVerified={(next) => {
            // Cross-card concurrency: merge ONLY phone fields. In-progress
            // first_name/last_name/date_of_birth draft in `profileForm` must
            // survive a phone-verify completion that happens mid-edit.
            setProfile((prev) =>
              prev
                ? {
                    ...prev,
                    phone: next.phone,
                    phone_verified_at: next.phone_verified_at,
                  }
                : next,
            );
            setPhoneModal({ open: false });
          }}
        />
      )}
    </div>
  );
}
