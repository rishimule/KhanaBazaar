"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { use, useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import CustomerStatusPill from "@/components/admin/CustomerStatusPill";
import { useAuth } from "@/lib/AuthContext";
import { fetchCustomerHub } from "@/lib/adminCustomers";
import type { AdminCustomerHub } from "@/types";
import styles from "./tabs.module.css";

function fmtDateTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : "—";
}

export default function CustomerOverviewTab({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const t = useTranslations("Admin.customers");
  const tc = useTranslations("Admin.common");
  const { token } = useAuth();
  const [hub, setHub] = useState<AdminCustomerHub | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setHub(await fetchCustomerHub(Number(id), token));
    } catch {
      setError(true);
    }
  }, [id, token]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial load sets state inside async callbacks
    load();
  }, [load]);

  if (error) return <div className={styles.errorBox}>{t("loadError")}</div>;
  if (!hub) return <div className={styles.state}>{tc("loading")}</div>;

  return (
    <div>
      <h2 className={styles.heading}>{t("overview.heading")}</h2>
      <div className={styles.detailsGrid}>
        <div className={styles.detailRow}>
          <span className={styles.detailLabel}>{t("overview.status")}</span>
          <span className={styles.detailValue}>
            <CustomerStatusPill status={hub.account_status} />
          </span>
        </div>
        <div className={styles.detailRow}>
          <span className={styles.detailLabel}>
            {t("overview.statusChanged")}
          </span>
          <span className={styles.detailValue}>
            {fmtDateTime(hub.status_changed_at)}
          </span>
        </div>
        <div className={styles.detailRow}>
          <span className={styles.detailLabel}>{t("overview.reason")}</span>
          <span className={styles.detailValue}>{hub.status_reason || "—"}</span>
        </div>
        <div className={styles.detailRow}>
          <span className={styles.detailLabel}>{t("overview.email")}</span>
          <span className={styles.detailValue}>{hub.email}</span>
        </div>
        <div className={styles.detailRow}>
          <span className={styles.detailLabel}>{t("overview.phone")}</span>
          <span className={styles.detailValue}>{hub.phone || "—"}</span>
        </div>
        <div className={styles.detailRow}>
          <span className={styles.detailLabel}>{t("stat.openOrders")}</span>
          <span className={styles.detailValue}>{hub.open_orders}</span>
        </div>
        <div className={styles.detailRow}>
          <span className={styles.detailLabel}>{t("stat.openCredit")}</span>
          <span className={styles.detailValue}>{hub.open_credit_accounts}</span>
        </div>
        <div className={styles.detailRow}>
          <span className={styles.detailLabel}>{t("overview.userId")}</span>
          <span className={styles.detailValue}>#{hub.user_id}</span>
        </div>
      </div>
    </div>
  );
}
