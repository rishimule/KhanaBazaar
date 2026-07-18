"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import {
  DeviceSession,
  listSessions,
  revokeSession,
  revokeAllSessions,
} from "@/lib/sessions";
import styles from "./DeviceSessionsPanel.module.css";

export default function DeviceSessionsPanel() {
  const t = useTranslations("Devices");
  const { token } = useAuth();
  const [sessions, setSessions] = useState<DeviceSession[] | null>(null);
  const [error, setError] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [busyAll, setBusyAll] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    setError(false);
    try {
      setSessions(await listSessions(token));
    } catch {
      setError(true);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const onRevoke = async (id: number) => {
    if (!token) return;
    setBusyId(id);
    try {
      await revokeSession(token, id);
      await load();
    } catch {
      setError(true);
    } finally {
      setBusyId(null);
    }
  };

  const onRevokeAll = async () => {
    if (!token) return;
    setBusyAll(true);
    try {
      await revokeAllSessions(token);
      await load();
    } catch {
      setError(true);
    } finally {
      setBusyAll(false);
    }
  };

  const fmt = (iso: string) => {
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  if (sessions === null && !error) {
    return <p className={styles.muted}>{t("loading")}</p>;
  }
  if (error) {
    return (
      <div className={styles.panel}>
        <p className={styles.error} role="alert">{t("error")}</p>
        <button className="btn btn-secondary" onClick={() => void load()}>↻</button>
      </div>
    );
  }

  const list = sessions ?? [];
  const hasOthers = list.some((s) => !s.current);

  return (
    <div className={styles.panel}>
      <p className={styles.subtitle}>{t("subtitle")}</p>
      {list.length === 0 ? (
        <p className={styles.muted}>{t("empty")}</p>
      ) : (
        <ul className={styles.list}>
          {list.map((s) => (
            <li key={s.id} className={styles.card}>
              <div className={styles.icon} aria-hidden>💻</div>
              <div className={styles.body}>
                <div className={styles.titleRow}>
                  <span className={styles.deviceLabel}>{s.device_label}</span>
                  {s.current && <span className={styles.currentPill}>{t("thisDevice")}</span>}
                </div>
                <div className={styles.meta}>{t("lastActive", { when: fmt(s.last_used_at) })}</div>
                {s.ip && <div className={styles.meta}>{s.ip}</div>}
              </div>
              {!s.current && (
                <button
                  className={styles.logoutBtn}
                  disabled={busyId === s.id}
                  onClick={() => void onRevoke(s.id)}
                >
                  {t("logOut")}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {hasOthers && (
        <button
          className="btn btn-secondary"
          disabled={busyAll}
          onClick={() => void onRevokeAll()}
        >
          {t("logOutOthers")}
        </button>
      )}
    </div>
  );
}
