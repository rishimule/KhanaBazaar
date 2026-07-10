"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { use, useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { useAuth } from "@/lib/AuthContext";
import {
  type SellerCreditConfig,
  getAdminCreditConfig,
  patchAdminCreditConfig,
} from "@/lib/credit";
import styles from "./page.module.css";

export default function AdminSellerCreditsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const sellerId = Number(id);
  const t = useTranslations("Credit");
  const { token } = useAuth();

  const [enabled, setEnabled] = useState(false);
  const [cap, setCap] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedOk, setSavedOk] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    getAdminCreditConfig(token, sellerId)
      .then((cfg: SellerCreditConfig) => {
        setEnabled(cfg.credit_enabled);
        setCap(String(cfg.max_limit_per_customer));
      })
      .catch(() => setError(t("errGeneric")))
      .finally(() => setLoading(false));
  }, [token, sellerId, t]);

  const save = async () => {
    if (!token) return;
    const capValue = Number(cap);
    if (!Number.isFinite(capValue) || capValue < 0) {
      setError(t("errInvalidCap"));
      return;
    }
    setSaving(true);
    setError(null);
    setSavedOk(false);
    try {
      const cfg = await patchAdminCreditConfig(token, sellerId, {
        credit_enabled: enabled,
        max_limit_per_customer: capValue,
      });
      setEnabled(cfg.credit_enabled);
      setCap(String(cfg.max_limit_per_customer));
      setSavedOk(true);
    } catch {
      setError(t("errGeneric"));
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className={styles.muted}>{t("loading")}</div>;

  return (
    <div className={styles.page}>
      <section className={styles.card}>
        <h2 className={styles.cardTitle}>{t("adminSettingsTitle")}</h2>
        <div className={styles.toggleRow}>
          <div>
            <div className={styles.toggleLabel}>{t("adminEnableLabel")}</div>
            <div className={styles.help}>{t("adminEnableHelp")}</div>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={enabled}
            aria-label={t("adminEnableLabel")}
            className={enabled ? styles.toggleOn : styles.toggleOff}
            onClick={() => setEnabled((v) => !v)}
          >
            <span className={styles.toggleKnob} />
          </button>
        </div>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="cap">{t("adminCapLabel")}</label>
          <input
            id="cap"
            className={styles.input}
            value={cap}
            onChange={(e) => setCap(e.target.value)}
            inputMode="numeric"
          />
          <p className={styles.help}>{t("adminCapHelp")}</p>
        </div>
        <div className={styles.actions}>
          <button className="btn btn-primary" type="button" onClick={save} disabled={saving}>
            {saving ? t("saving") : t("save")}
          </button>
          {savedOk && <span className={styles.toast}>{t("saved")}</span>}
        </div>
        {error && <div className={styles.errorText} role="alert">{error}</div>}
      </section>
    </div>
  );
}
