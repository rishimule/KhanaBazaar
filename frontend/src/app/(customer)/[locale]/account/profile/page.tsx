"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { get, patch } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { apiErrorKey } from "@/lib/errors";
import type { CustomerProfile } from "@/types";
import styles from "./page.module.css";

interface ProfileForm {
  first_name: string;
  last_name: string;
  phone: string;
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

const PHONE_RE = /^[0-9+() -]{7,20}$/;

function profileFormFrom(profile: CustomerProfile): ProfileForm {
  return {
    first_name: profile.first_name,
    last_name: profile.last_name ?? "",
    phone: profile.phone ?? "",
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

function validationErrorsForPrefix(
  error: unknown,
  prefix: string,
): Record<string, string> {
  const detail = (error as { detail?: unknown })?.detail;
  if (!Array.isArray(detail)) return {};
  return detail.reduce<Record<string, string>>(
    (acc, issue: FastApiValidationIssue) => {
      if (!Array.isArray(issue.loc) || typeof issue.msg !== "string") return acc;
      const prefixIndex = issue.loc.indexOf(prefix);
      if (prefixIndex === -1) return acc;
      const field = issue.loc[prefixIndex + 1];
      if (typeof field === "string") acc[field] = issue.msg;
      return acc;
    },
    {},
  );
}

function normalizeOptional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
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
  const [profileForm, setProfileForm] = useState<ProfileForm>({
    first_name: "",
    last_name: "",
    phone: "",
  });
  const [profileErrors, setProfileErrors] = useState<ProfileErrors>({});
  const [sectionError, setSectionError] = useState<string | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);

  useEffect(() => {
    if (!token) {
      setLoadingProfile(false);
      setSectionError(t("loadError"));
      return;
    }
    let active = true;
    setLoadingProfile(true);
    get<CustomerProfile>("/api/v1/customers/me", token)
      .then((data) => {
        if (!active) return;
        setProfile(data);
        setProfileForm(profileFormFrom(data));
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
        },
        token,
      );
      setProfile(next);
      setProfileForm(profileFormFrom(next));
      setProfileErrors({});
    } catch (error) {
      setProfileErrors(validationErrorsForPrefix(error, "body") as ProfileErrors);
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

        <form className={styles.profileForm} onSubmit={saveProfile}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="first-name">
              {t("firstNameLabel")}
            </label>
            <input
              id="first-name"
              className={`${styles.input} ${profileErrors.first_name ? styles.inputError : ""}`}
              value={profileForm.first_name}
              onChange={(event) =>
                setProfileForm((curr) => ({ ...curr, first_name: event.target.value }))
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
              className={`${styles.input} ${profileErrors.last_name ? styles.inputError : ""}`}
              value={profileForm.last_name}
              onChange={(event) =>
                setProfileForm((curr) => ({ ...curr, last_name: event.target.value }))
              }
              maxLength={80}
            />
            {profileErrors.last_name && (
              <span className={styles.errorText}>{profileErrors.last_name}</span>
            )}
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="phone">
              {t("phoneLabel")}
            </label>
            <input
              id="phone"
              className={`${styles.input} ${profileErrors.phone ? styles.inputError : ""}`}
              value={profileForm.phone}
              onChange={(event) =>
                setProfileForm((curr) => ({ ...curr, phone: event.target.value }))
              }
              inputMode="tel"
              maxLength={20}
            />
            {profileErrors.phone && (
              <span className={styles.errorText}>{profileErrors.phone}</span>
            )}
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
    </div>
  );
}
