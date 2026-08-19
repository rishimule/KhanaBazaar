"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { apiErrorCode } from "@/lib/errors";
import { setServiceReturnWindow } from "@/lib/returns";
import type { SellerProfile, Service } from "@/types";
import styles from "./ReturnWindowCard.module.css";

interface ServiceWithWindow extends Service {
  return_window_days?: number;
}

/**
 * Per-service return window. Uses its own endpoint rather than the general
 * service-settings PATCH, which rejects approved sellers and routes them
 * through a change request — a return window is operational, like pausing.
 */
export default function ReturnWindowCard() {
  const t = useTranslations("Seller.returns");
  const { token } = useAuth();
  const [services, setServices] = useState<ServiceWithWindow[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [savingId, setSavingId] = useState<number | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        // There is no GET /sellers/me/services — the seller's services come
        // back on the profile payload.
        const profile = await get<SellerProfile>(
          "/api/v1/sellers/me/profile",
          token
        );
        const data = (profile.services ?? []) as ServiceWithWindow[];
        if (cancelled) return;
        setServices(data);
        setDrafts(
          Object.fromEntries(
            data.map((s) => [s.id, String(s.return_window_days ?? 0)])
          )
        );
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const save = async (serviceId: number) => {
    if (!token) return;
    const raw = (drafts[serviceId] ?? "").trim();
    if (raw === "") {
      setError(t("errors.invalid_return_window"));
      return;
    }
    const days = Number(raw);
    setSavingId(serviceId);
    setError(null);
    setToast(null);
    try {
      await setServiceReturnWindow(token, serviceId, days);
      setServices((prev) =>
        prev
          ? prev.map((s) =>
              s.id === serviceId ? { ...s, return_window_days: days } : s
            )
          : prev
      );
      setToast(t("windowSaved"));
    } catch (e) {
      setError(
        apiErrorCode(e) === "invalid_return_window"
          ? t("errors.invalid_return_window")
          : t("errors.unknown")
      );
    } finally {
      setSavingId(null);
    }
  };

  if (failed) {
    return (
      <section className={styles.card}>
        <h2 className={styles.title}>{t("windowTitle")}</h2>
        <p role="alert" className={styles.error}>
          {t("loadFailed")}
        </p>
      </section>
    );
  }
  if (!services) return null;

  return (
    <section className={styles.card}>
      <h2 className={styles.title}>{t("windowTitle")}</h2>
      <p className={styles.muted}>{t("windowIntro")}</p>
      <ul className={styles.list}>
        {services.map((service) => (
          <li key={service.id} className={styles.row}>
            <span className={styles.serviceName}>{service.name}</span>
            <input
              type="number"
              min={0}
              max={365}
              className={styles.input}
              value={drafts[service.id] ?? "0"}
              aria-label={t("windowFieldLabel", { service: service.name })}
              onChange={(e) =>
                setDrafts((d) => ({ ...d, [service.id]: e.target.value }))
              }
              required
            />
            <span className={styles.unit}>
              {Number(drafts[service.id]) === 0 ? t("windowOff") : t("windowDays")}
            </span>
            <button
              type="button"
              className="btn"
              disabled={savingId === service.id}
              onClick={() => save(service.id)}
            >
              {t("save")}
            </button>
          </li>
        ))}
      </ul>
      {toast && <p className={styles.toast}>{toast}</p>}
      {error && (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      )}
    </section>
  );
}
