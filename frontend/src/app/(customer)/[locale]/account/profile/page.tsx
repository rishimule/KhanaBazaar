"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import PhoneVerifyModal from "@/components/PhoneVerifyModal";
import { get, patch } from "@/lib/api";
import { getCustomerStats } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import { apiErrorKey } from "@/lib/errors";
import type { CustomerProfile, CustomerStats } from "@/types";
import styles from "./page.module.css";

interface ProfileForm {
  first_name: string;
  last_name: string;
  phone: string;
  date_of_birth: string;
}

interface ProfileErrors {
  first_name?: string;
  last_name?: string;
  phone?: string;
}

interface FastApiValidationIssue {
  loc?: Array<string | number>;
  msg?: string;
}

const PHONE_RE = /^\+91\d{10}$/;
const PHONE_PREFIX = "+91";

function phoneDigitsFromIntl(phone: string): string {
  if (!phone) return "";
  const trimmed = phone.replace(/[\s\-()]/g, "");
  const withoutPrefix = trimmed.startsWith(PHONE_PREFIX)
    ? trimmed.slice(PHONE_PREFIX.length)
    : trimmed.replace(/^\+?91/, "");
  return withoutPrefix.replace(/\D/g, "").slice(0, 10);
}

function intlFromPhoneDigits(digits: string): string {
  const cleaned = digits.replace(/\D/g, "").slice(0, 10);
  return cleaned.length > 0 ? `${PHONE_PREFIX}${cleaned}` : "";
}

function profileFormFrom(profile: CustomerProfile): ProfileForm {
  return {
    first_name: profile.first_name,
    last_name: profile.last_name ?? "",
    phone: profile.phone ?? "",
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

function initialsAndColor(name: string, email: string): { initials: string; color: string } {
  const parts = name.trim().split(/\s+/);
  const initials =
    (parts[0]?.charAt(0) ?? "") + (parts[1]?.charAt(0) ?? "");
  const hue = [...email].reduce((a, c) => a + c.charCodeAt(0), 0) % 360;
  return {
    initials: (initials || "U").toUpperCase(),
    color: `hsl(${hue}deg 60% 50%)`,
  };
}

export default function AccountProfilePage() {
  const { token } = useAuth();
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
  const [profileForm, setProfileForm] = useState<ProfileForm>({
    first_name: "",
    last_name: "",
    phone: "",
    date_of_birth: "",
  });
  const [profileErrors, setProfileErrors] = useState<ProfileErrors>({});
  const [sectionError, setSectionError] = useState<string | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);
  const [verifyOpen, setVerifyOpen] = useState(false);

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

  const validateProfile = (): ProfileErrors => {
    const errors: ProfileErrors = {};
    if (!profileForm.first_name.trim()) {
      errors.first_name = t("firstNameRequired");
    }
    if (profileForm.phone.trim() && !PHONE_RE.test(profileForm.phone.trim())) {
      errors.phone = t("phoneInvalid");
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
          phone: normalizeOptional(profileForm.phone),
          date_of_birth: normalizeOptional(profileForm.date_of_birth),
        },
        token,
      );
      setProfile(next);
      setProfileForm(profileFormFrom(next));
      setProfileErrors({});
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

  const { initials, color } = initialsAndColor(
    `${profile.first_name} ${profile.last_name ?? ""}`.trim(),
    profile.email,
  );
  const memberSince = profile.phone_verified_at; // placeholder if you prefer createdAt

  return (
    <div className={styles.page}>
      {sectionError && <div className={styles.errorBanner}>{sectionError}</div>}

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <h2 className={styles.sectionTitle}>{t("profileSection")}</h2>
            <p className={styles.sectionSubtitle}>{profile.email}</p>
          </div>
        </div>

        <div className={styles.avatarRow}>
          <div className={styles.avatar} style={{ background: color }}>
            {initials}
          </div>
          <div>
            <div className={styles.avatarLabel}>
              {profile.first_name} {profile.last_name ?? ""}
            </div>
            <div className={styles.avatarEmail}>{profile.email}</div>
          </div>
        </div>

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
            <label className={styles.label} htmlFor="phone">
              {t("phoneLabel")}
            </label>
            <div className={styles.verifyRow}>
              <div className={styles.phoneInputWrap}>
                <span className={styles.phonePrefix} aria-hidden="true">
                  {PHONE_PREFIX}
                </span>
                <input
                  id="phone"
                  className={`${styles.input} ${styles.phoneInput} ${profileErrors.phone ? styles.inputError : ""}`}
                  value={phoneDigitsFromIntl(profileForm.phone)}
                  onChange={(e) =>
                    setProfileForm((c) => ({
                      ...c,
                      phone: intlFromPhoneDigits(e.target.value),
                    }))
                  }
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={10}
                  placeholder="9876543210"
                  autoComplete="tel-national"
                  aria-describedby="phone-prefix-hint"
                />
              </div>
              {profile.phone_verified_at ? (
                <span className={styles.verifiedBadge}>✓ {t("verified")}</span>
              ) : (
                <button
                  type="button"
                  className="btn btn-outline"
                  onClick={() => setVerifyOpen(true)}
                >
                  {t("verifyPhone")}
                </button>
              )}
            </div>
            <span id="phone-prefix-hint" className={styles.phoneHint}>
              {t("phoneIndiaHint")}
            </span>
            {profileErrors.phone && (
              <span className={styles.errorText}>{profileErrors.phone}</span>
            )}
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
          </div>
        </form>
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
          {memberSince && (
            <div className={styles.statItem}>
              <span className={styles.statLabel}>{t("phoneVerifiedSince")}</span>
              <span className={styles.statValue} suppressHydrationWarning>
                {new Date(memberSince).toLocaleDateString()}
              </span>
            </div>
          )}
        </div>
      </section>

      {verifyOpen && (
        <PhoneVerifyModal
          currentPhone={profile.phone ?? profileForm.phone ?? null}
          onClose={() => setVerifyOpen(false)}
          onVerified={(next) => {
            setProfile(next);
            setProfileForm(profileFormFrom(next));
          }}
        />
      )}
    </div>
  );
}
