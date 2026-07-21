"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { use, useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { fetchCustomerNotifications } from "@/lib/adminCustomers";
import type { AdminCustomerNotification } from "@/types";
import styles from "../tabs.module.css";

export default function CustomerNotificationsTab({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const t = useTranslations("Admin.customers");
  const tc = useTranslations("Admin.common");
  const { token } = useAuth();
  const [rows, setRows] = useState<AdminCustomerNotification[] | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setRows(await fetchCustomerNotifications(Number(id), token));
    } catch {
      setError(true);
    }
  }, [id, token]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial load sets state inside async callbacks
    load();
  }, [load]);

  if (error)
    return <div className={styles.errorBox}>{t("notifications.loadError")}</div>;
  if (!rows) return <div className={styles.state}>{tc("loading")}</div>;

  return (
    <div>
      <h2 className={styles.heading}>{t("notifications.heading")}</h2>
      {rows.length === 0 ? (
        <div className={styles.empty}>{t("notifications.empty")}</div>
      ) : (
        <div className={styles.notifList}>
          {rows.map((n) => (
            <div
              key={n.id}
              className={`${styles.notif} ${n.read ? "" : styles.notifUnread}`}
            >
              <div className={styles.notifHead}>
                {!n.read && <span className={styles.notifDot} aria-hidden />}
                <span className={styles.notifTitle}>{n.title}</span>
              </div>
              <div className={styles.notifBody}>{n.body}</div>
              <div className={styles.notifMeta}>
                {n.type} · {new Date(n.created_at).toLocaleString()}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
