"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";

import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { submitOnboardingRequest } from "@/lib/onboarding";
import styles from "./page.module.css";

function SuggestStoreInner() {
  const t = useTranslations("SuggestStore");
  const { dbUser } = useAuth();
  const { location, userSet } = useDeliveryLocation();
  const sp = useSearchParams();

  const [form, setForm] = useState({
    store_name: "",
    contact_phone: "",
    contact_email: dbUser?.email ?? "",
    contact_address: "",
    preferred_categories: "",
  });
  const [state, setState] = useState<"idle" | "submitting" | "done">("idle");
  const [error, setError] = useState<string | null>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  function update(field: keyof typeof form, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (
      !form.store_name.trim() ||
      !form.contact_phone.trim() ||
      !form.contact_email.trim() ||
      !form.contact_address.trim()
    ) {
      setError(t("errorRequired"));
      return;
    }

    setState("submitting");
    try {
      await submitOnboardingRequest({
        store_name: form.store_name.trim(),
        contact_phone: form.contact_phone.trim(),
        contact_email: form.contact_email.trim(),
        contact_address: form.contact_address.trim(),
        preferred_categories: form.preferred_categories.trim() || null,
        area_label: sp.get("area") ?? (userSet ? location.label : null),
        area_lat: userSet ? location.lat : null,
        area_lng: userSet ? location.lng : null,
        source: sp.get("source"),
      });
      setState("done");
    } catch (err) {
      setState("idle");
      if (err instanceof ApiError) {
        const detail = err.detail as unknown as { error?: string } | string;
        const code = typeof detail === "object" ? detail?.error : undefined;
        if (err.status === 429) {
          setError(t("errorRateLimited"));
          return;
        }
        if (err.status === 422 && code === "phone_invalid") {
          setError(t("errorPhone"));
          return;
        }
      }
      setError(t("errorGeneric"));
    }
  }

  if (state === "done") {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <span className={styles.successIcon} aria-hidden="true">
            ✅
          </span>
          <h1 className={styles.title}>{t("successTitle")}</h1>
          <p className={styles.intro}>{t("successBody")}</p>
          <Link href="/" className="btn btn-primary">
            {t("backToBrowsing")}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <h1 className={styles.title}>{t("title")}</h1>
        <p className={styles.intro}>{t("intro")}</p>

        <form className={styles.form} onSubmit={handleSubmit} noValidate>
          <label className={styles.field}>
            <span className={styles.label}>
              {t("storeName")} <span aria-hidden="true" className={styles.req}>*</span>
            </span>
            <input
              className={styles.input}
              type="text"
              value={form.store_name}
              onChange={(e) => update("store_name", e.target.value)}
              maxLength={120}
              required
              autoComplete="organization"
            />
          </label>

          <label className={styles.field}>
            <span className={styles.label}>
              {t("phone")} <span aria-hidden="true" className={styles.req}>*</span>
            </span>
            <input
              className={styles.input}
              type="tel"
              value={form.contact_phone}
              onChange={(e) => update("contact_phone", e.target.value)}
              maxLength={20}
              required
              autoComplete="tel"
              placeholder="+919812345678"
            />
          </label>

          <label className={styles.field}>
            <span className={styles.label}>
              {t("email")} <span aria-hidden="true" className={styles.req}>*</span>
            </span>
            <input
              className={styles.input}
              type="email"
              value={form.contact_email}
              onChange={(e) => update("contact_email", e.target.value)}
              maxLength={254}
              required
              autoComplete="email"
            />
          </label>

          <label className={styles.field}>
            <span className={styles.label}>
              {t("address")} <span aria-hidden="true" className={styles.req}>*</span>
            </span>
            <textarea
              className={styles.textarea}
              value={form.contact_address}
              onChange={(e) => update("contact_address", e.target.value)}
              maxLength={500}
              rows={3}
              required
            />
          </label>

          <label className={styles.field}>
            <span className={styles.label}>
              {t("preferredCategories")}{" "}
              <span className={styles.optional}>({t("optional")})</span>
            </span>
            <input
              className={styles.input}
              type="text"
              value={form.preferred_categories}
              onChange={(e) => update("preferred_categories", e.target.value)}
              maxLength={300}
            />
          </label>

          {error && (
            <p className={styles.error} role="alert" ref={errorRef} tabIndex={-1}>
              {error}
            </p>
          )}

          <button
            type="submit"
            className="btn btn-primary"
            disabled={state === "submitting"}
            aria-busy={state === "submitting"}
          >
            {state === "submitting" ? t("submitting") : t("submit")}
          </button>
        </form>
      </div>
    </div>
  );
}

export default function SuggestStorePage() {
  return (
    <Suspense fallback={<div className={styles.page} />}>
      <SuggestStoreInner />
    </Suspense>
  );
}
