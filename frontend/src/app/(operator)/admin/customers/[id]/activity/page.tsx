"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { use, useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { fetchCustomerActivity } from "@/lib/adminCustomers";
import type { AdminCustomerActivity } from "@/types";
import styles from "../tabs.module.css";

export default function CustomerActivityTab({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const t = useTranslations("Admin.customers");
  const tc = useTranslations("Admin.common");
  const { token } = useAuth();
  const [rows, setRows] = useState<AdminCustomerActivity[] | null>(null);
  const [error, setError] = useState(false);

  // Statuses in the log are the lifecycle enum; fall back to the raw value if a
  // future status has no translation yet.
  const statusLabel = (s: string): string =>
    t.has(`status.${s}`) ? t(`status.${s}`) : s;

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setRows(await fetchCustomerActivity(Number(id), token));
    } catch {
      setError(true);
    }
  }, [id, token]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial load sets state inside async callbacks
    load();
  }, [load]);

  if (error) return <div className={styles.errorBox}>{t("activity.loadError")}</div>;
  if (!rows) return <div className={styles.state}>{tc("loading")}</div>;

  return (
    <div>
      <h2 className={styles.heading}>{t("activity.heading")}</h2>
      {rows.length === 0 ? (
        <div className={styles.empty}>{t("activity.empty")}</div>
      ) : (
        <div className={styles.timeline}>
          {rows.map((ev) => (
            <div key={ev.id} className={styles.event}>
              <div className={styles.eventHead}>
                <span className={styles.transition}>
                  {ev.from_status
                    ? t("activity.transition", {
                        from: statusLabel(ev.from_status),
                        to: statusLabel(ev.to_status),
                      })
                    : statusLabel(ev.to_status)}
                </span>
                <span className={styles.eventMeta}>
                  {t("activity.byActor", { role: ev.actor_role })}
                </span>
              </div>
              <div className={styles.eventMeta}>
                {new Date(ev.created_at).toLocaleString()}
              </div>
              {ev.reason && <div className={styles.eventReason}>{ev.reason}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
