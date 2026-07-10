"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import DataTable, { Column } from "@/components/DataTable";
import Modal from "@/components/Modal";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import {
  type CreditAccount,
  type SellerCreditConfig,
  getSellerCreditConfig,
  grantCredit,
  listSellerCreditAccounts,
  patchCreditAccount,
  recordRepayment,
} from "@/lib/credit";
import styles from "./page.module.css";

const money = (n: number) => `₹${n.toFixed(2)}`;

export default function SellerCreditPage() {
  const t = useTranslations("Credit");
  const { token } = useAuth();

  const [config, setConfig] = useState<SellerCreditConfig | null>(null);
  const [accounts, setAccounts] = useState<CreditAccount[]>([]);
  const [loading, setLoading] = useState(true);

  // grant form
  const [contact, setContact] = useState("");
  const [limit, setLimit] = useState("");
  const [granting, setGranting] = useState(false);
  const [grantError, setGrantError] = useState<string | null>(null);
  const [grantOk, setGrantOk] = useState(false);

  // repayment modal
  const [repayTarget, setRepayTarget] = useState<CreditAccount | null>(null);
  const [repayAmount, setRepayAmount] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  const refetch = useCallback(() => {
    if (!token) return;
    setLoading(true);
    Promise.all([getSellerCreditConfig(token), listSellerCreditAccounts(token)])
      .then(([cfg, accts]) => {
        setConfig(cfg);
        setAccounts(accts);
      })
      .catch(() => setAccounts([]))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const grant = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!token) return;
    const value = Number(limit);
    if (!contact.trim() || !Number.isFinite(value) || value <= 0) {
      setGrantError(t("errInvalidGrant"));
      return;
    }
    setGranting(true);
    setGrantError(null);
    setGrantOk(false);
    const isEmail = contact.includes("@");
    try {
      await grantCredit(token, {
        customer_email: isEmail ? contact.trim() : undefined,
        customer_phone: isEmail ? undefined : contact.trim(),
        credit_limit: value,
      });
      setGrantOk(true);
      setContact("");
      setLimit("");
      refetch();
    } catch (err) {
      const code =
        err instanceof ApiError
          ? (err.detail as unknown as { error?: string })?.error
          : null;
      setGrantError(code ? t(`err_${code}`) : t("errGeneric"));
    } finally {
      setGranting(false);
    }
  };

  const toggleStatus = async (acct: CreditAccount) => {
    if (!token) return;
    setBusyId(acct.id);
    try {
      await patchCreditAccount(token, acct.id, {
        status: acct.status === "active" ? "suspended" : "active",
      });
      refetch();
    } finally {
      setBusyId(null);
    }
  };

  const submitRepay = async () => {
    if (!token || !repayTarget) return;
    const value = Number(repayAmount);
    if (!Number.isFinite(value) || value <= 0) return;
    setBusyId(repayTarget.id);
    try {
      await recordRepayment(token, repayTarget.id, { amount: value });
      setRepayTarget(null);
      setRepayAmount("");
      refetch();
    } catch (err) {
      const code =
        err instanceof ApiError
          ? (err.detail as unknown as { error?: string })?.error
          : null;
      setGrantError(code ? t(`err_${code}`) : t("errGeneric"));
      setRepayTarget(null);
    } finally {
      setBusyId(null);
    }
  };

  const columns: Column<CreditAccount>[] = [
    { key: "customer_profile_id", label: t("colCustomer"), render: (r) => `#${r.customer_profile_id}` },
    { key: "credit_limit", label: t("colLimit"), render: (r) => money(r.credit_limit) },
    { key: "outstanding_balance", label: t("colOutstanding"), render: (r) => money(r.outstanding_balance) },
    { key: "available", label: t("colAvailable"), render: (r) => money(r.available) },
    {
      key: "status",
      label: t("colStatus"),
      render: (r) => (
        <span className={r.status === "active" ? styles.chipActive : styles.chipSuspended}>
          {t(`status_${r.status}`)}
        </span>
      ),
    },
    {
      key: "actions",
      label: t("colActions"),
      render: (r) => (
        <div className={styles.actions}>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busyId === r.id || r.outstanding_balance <= 0}
            onClick={() => {
              setRepayTarget(r);
              setRepayAmount("");
            }}
          >
            {t("recordRepayment")}
          </button>
          <button
            type="button"
            className={styles.linkBtn}
            disabled={busyId === r.id}
            onClick={() => toggleStatus(r)}
          >
            {r.status === "active" ? t("suspend") : t("resume")}
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      {config != null && (
        <div className={config.credit_enabled ? styles.banner : styles.bannerOff}>
          {config.credit_enabled
            ? t("capBanner", { amount: config.max_limit_per_customer.toFixed(0) })
            : t("notEnabled")}
        </div>
      )}

      {config?.credit_enabled && (
        <section className={styles.card}>
          <h2 className={styles.cardTitle}>{t("grantTitle")}</h2>
          <form className={styles.form} onSubmit={grant}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="credit-contact">{t("contactLabel")}</label>
              <input
                id="credit-contact"
                className={styles.input}
                value={contact}
                onChange={(e) => setContact(e.target.value)}
                placeholder={t("contactPlaceholder")}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="credit-limit">{t("limitLabel")}</label>
              <input
                id="credit-limit"
                className={styles.input}
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
                inputMode="numeric"
                placeholder={t("limitPlaceholder", { amount: (config?.max_limit_per_customer ?? 0).toFixed(0) })}
              />
            </div>
            <div className={styles.actions}>
              <button className="btn btn-primary" type="submit" disabled={granting}>
                {granting ? t("granting") : t("grant")}
              </button>
              {grantOk && <span className={styles.toast}>{t("grantOk")}</span>}
            </div>
            {grantError && <div className={styles.errorText} role="alert">{grantError}</div>}
          </form>
        </section>
      )}

      <section className={styles.card}>
        <h2 className={styles.cardTitle}>{t("accountsTitle")}</h2>
        {loading ? (
          <p className={styles.muted}>{t("loading")}</p>
        ) : (
          <DataTable columns={columns} data={accounts} keyField="id" emptyMessage={t("empty")} />
        )}
      </section>

      {repayTarget && (
        <Modal
          title={t("repayTitle")}
          onClose={() => setRepayTarget(null)}
          footer={
            <>
              <button type="button" className="btn btn-secondary" onClick={() => setRepayTarget(null)}>
                {t("cancel")}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!repayAmount.trim() || busyId === repayTarget.id}
                onClick={submitRepay}
              >
                {t("recordRepayment")}
              </button>
            </>
          }
        >
          <p className={styles.muted}>
            {t("repayOutstanding", { amount: money(repayTarget.outstanding_balance) })}
          </p>
          <label className={styles.label} htmlFor="repay-amount">{t("amountLabel")}</label>
          <input
            id="repay-amount"
            className={styles.input}
            value={repayAmount}
            onChange={(e) => setRepayAmount(e.target.value)}
            inputMode="numeric"
          />
        </Modal>
      )}
    </div>
  );
}
