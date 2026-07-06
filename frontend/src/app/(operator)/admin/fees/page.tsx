// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import type { Service } from "@/types";
import {
  getFeeSettings,
  patchFeeSettings,
  getServiceFeeConfig,
  patchServiceFeeConfig,
  putServicePlans,
  type PlatformFeeSettings,
  type ServiceFeeConfig,
  type SubscriptionPlanItem,
} from "@/lib/adminFees";
import styles from "./page.module.css";

// Coerce a number-input string; empty/invalid → 0 (avoids NaN in controlled
// inputs and NaN→null serialization to the backend).
function toNum(v: string): number {
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

export default function AdminFeesPage() {
  const { token } = useAuth();
  const [settings, setSettings] = useState<PlatformFeeSettings | null>(null);
  const [services, setServices] = useState<Service[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsMsg, setSettingsMsg] = useState<string | null>(null);

  const [serviceId, setServiceId] = useState<number | null>(null);
  const [config, setConfig] = useState<ServiceFeeConfig | null>(null);
  const [plans, setPlans] = useState<SubscriptionPlanItem[]>([]);
  const [savingConfig, setSavingConfig] = useState(false);
  const [configMsg, setConfigMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    Promise.all([
      getFeeSettings(token),
      get<{ items: Service[] }>("/api/v1/catalog/admin/services?page_size=100", token),
    ])
      .then(([s, svcs]) => {
        setSettings(s);
        setServices(svcs.items);
        if (svcs.items.length > 0) setServiceId(svcs.items[0].id);
      })
      .catch(() => setLoadError("Couldn't load fee settings."));
  }, [token]);

  const loadConfig = useCallback(
    (sid: number) => {
      if (!token) return;
      setConfig(null);
      setConfigMsg(null);
      getServiceFeeConfig(token, sid)
        .then((r) => {
          setConfig(r.config);
          setPlans(
            [3, 6, 12].map((d) => {
              const found = r.plans.find((p) => p.duration_months === d);
              return found ?? { duration_months: d, price: 0, is_active: false };
            }),
          );
        })
        .catch(() => setConfigMsg("Couldn't load this service's config."));
    },
    [token],
  );

  useEffect(() => {
    if (serviceId != null) loadConfig(serviceId);
  }, [serviceId, loadConfig]);

  function setS<K extends keyof PlatformFeeSettings>(key: K, value: PlatformFeeSettings[K]) {
    setSettings((prev) => (prev ? { ...prev, [key]: value } : prev));
  }
  function setC<K extends keyof ServiceFeeConfig>(key: K, value: ServiceFeeConfig[K]) {
    setConfig((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  async function saveSettings() {
    if (!settings || !token) return;
    setSavingSettings(true);
    setSettingsMsg(null);
    try {
      const saved = await patchFeeSettings(token, settings);
      setSettings(saved);
      setSettingsMsg("Saved.");
    } catch {
      setSettingsMsg("Save failed. Please try again.");
    } finally {
      setSavingSettings(false);
    }
  }

  async function saveConfig() {
    if (!config || serviceId == null || !token) return;
    setSavingConfig(true);
    setConfigMsg(null);
    try {
      await patchServiceFeeConfig(token, serviceId, config);
      await putServicePlans(token, serviceId, plans);
      setConfigMsg("Saved.");
    } catch {
      setConfigMsg("Save failed. Please try again.");
    } finally {
      setSavingConfig(false);
    }
  }

  if (loadError) return <div className={styles.errorBanner} role="alert">{loadError}</div>;
  if (!settings) return <div className={styles.loader}>Loading…</div>;

  return (
    <div className={styles.page}>
      <p className={styles.intro}>
        Configure global payment details and, per service, which fee models sellers can opt into.
      </p>

      {/* ── Global settings ─────────────────────────────────────────── */}
      <section className={styles.card}>
        <h2 className={styles.cardTitle}>Global settings</h2>
        <div className={styles.grid}>
          <label className={styles.field}>
            <span>Grace period (days)</span>
            <input type="number" min={0} max={30} value={settings.grace_period_days}
              onChange={(e) => setS("grace_period_days", toNum(e.target.value))} />
          </label>
          <label className={styles.field}>
            <span>Expiry reminder start (days)</span>
            <input type="number" min={1} max={30} value={settings.expiry_reminder_start_days}
              onChange={(e) => setS("expiry_reminder_start_days", toNum(e.target.value))} />
          </label>
          <label className={styles.field}>
            <span>Pending-payment protection (days)</span>
            <input type="number" min={0} max={60} value={settings.pending_payment_protect_days}
              onChange={(e) => setS("pending_payment_protect_days", toNum(e.target.value))} />
          </label>
          <label className={styles.field}>
            <span>Bank account name</span>
            <input value={settings.bank_account_name ?? ""}
              onChange={(e) => setS("bank_account_name", e.target.value || null)} />
          </label>
          <label className={styles.field}>
            <span>Bank account number</span>
            <input value={settings.bank_account_number ?? ""}
              onChange={(e) => setS("bank_account_number", e.target.value || null)} />
          </label>
          <label className={styles.field}>
            <span>IFSC</span>
            <input value={settings.bank_ifsc ?? ""}
              onChange={(e) => setS("bank_ifsc", e.target.value || null)} />
          </label>
          <label className={styles.field}>
            <span>UPI ID</span>
            <input value={settings.upi_id ?? ""}
              onChange={(e) => setS("upi_id", e.target.value || null)} />
          </label>
          <label className={styles.field}>
            <span>GSTIN</span>
            <input value={settings.gstin ?? ""}
              onChange={(e) => setS("gstin", e.target.value || null)} />
          </label>
          <label className={`${styles.field} ${styles.wide}`}>
            <span>Payment QR image URL</span>
            <input value={settings.qr_image_url ?? ""} placeholder="https://…"
              onChange={(e) => setS("qr_image_url", e.target.value || null)} />
          </label>
        </div>
        {settings.qr_image_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img className={styles.qr} src={settings.qr_image_url} alt="Payment QR preview" referrerPolicy="no-referrer" />
        )}
        <div className={styles.actions}>
          <button type="button" className="btn btn-primary" disabled={savingSettings} onClick={saveSettings}>
            Save settings
          </button>
          {settingsMsg && <span className={styles.msg}>{settingsMsg}</span>}
        </div>
      </section>

      {/* ── Per-service config ──────────────────────────────────────── */}
      <section className={styles.card}>
        <h2 className={styles.cardTitle}>Per-service configuration</h2>
        <label className={styles.field}>
          <span>Service</span>
          <select value={serviceId ?? ""} onChange={(e) => setServiceId(toNum(e.target.value))}>
            {services.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </label>

        {!config ? (
          <div className={styles.loader}>Loading service…</div>
        ) : (
          <>
            <div className={styles.subgroup}>
              <label className={styles.check}>
                <input type="checkbox" checked={config.freebie_enabled}
                  onChange={(e) => setC("freebie_enabled", e.target.checked)} />
                <span>Freebie trial enabled</span>
              </label>
              <label className={styles.field}>
                <span>Freebie default (days)</span>
                <input type="number" min={0} max={365} value={config.freebie_default_days}
                  onChange={(e) => setC("freebie_default_days", toNum(e.target.value))} />
              </label>
            </div>

            <div className={styles.subgroup}>
              <label className={styles.check}>
                <input type="checkbox" checked={config.subscription_enabled}
                  onChange={(e) => setC("subscription_enabled", e.target.checked)} />
                <span>Subscription enabled</span>
              </label>
              <table className={styles.plans}>
                <thead>
                  <tr><th>Duration</th><th>Price (₹)</th><th>Active</th></tr>
                </thead>
                <tbody>
                  {plans.map((p, i) => (
                    <tr key={p.duration_months}>
                      <td>{p.duration_months} months</td>
                      <td>
                        <input type="number" min={0} value={p.price}
                          onChange={(e) => setPlans((prev) => prev.map((x, j) => j === i ? { ...x, price: toNum(e.target.value) } : x))} />
                      </td>
                      <td>
                        <input type="checkbox" checked={p.is_active}
                          onChange={(e) => setPlans((prev) => prev.map((x, j) => j === i ? { ...x, is_active: e.target.checked } : x))} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className={styles.subgroup}>
              <label className={styles.check}>
                <input type="checkbox" checked={config.order_value_enabled}
                  onChange={(e) => setC("order_value_enabled", e.target.checked)} />
                <span>Order-value % enabled (Phase 2)</span>
              </label>
              <div className={styles.grid}>
                <label className={styles.field}><span>Percent</span>
                  <input type="number" min={0} max={100} value={config.order_value_percent}
                    onChange={(e) => setC("order_value_percent", toNum(e.target.value))} /></label>
                <label className={styles.field}><span>Min deposit (₹)</span>
                  <input type="number" min={0} value={config.order_value_min_deposit}
                    onChange={(e) => setC("order_value_min_deposit", toNum(e.target.value))} /></label>
                <label className={styles.field}><span>Billing day</span>
                  <input type="number" min={1} max={28} value={config.order_value_billing_day}
                    onChange={(e) => setC("order_value_billing_day", toNum(e.target.value))} /></label>
              </div>
            </div>

            <div className={styles.subgroup}>
              <label className={styles.check}>
                <input type="checkbox" checked={config.pay_per_txn_enabled}
                  onChange={(e) => setC("pay_per_txn_enabled", e.target.checked)} />
                <span>Pay-per-transaction enabled (Phase 2)</span>
              </label>
              <div className={styles.grid}>
                <label className={styles.field}><span>Fee per order (₹)</span>
                  <input type="number" min={0} value={config.pay_per_txn_fee}
                    onChange={(e) => setC("pay_per_txn_fee", toNum(e.target.value))} /></label>
                <label className={styles.field}><span>Min deposit (₹)</span>
                  <input type="number" min={0} value={config.pay_per_txn_min_deposit}
                    onChange={(e) => setC("pay_per_txn_min_deposit", toNum(e.target.value))} /></label>
                <label className={styles.field}><span>Low-balance threshold (₹)</span>
                  <input type="number" min={0} value={config.pay_per_txn_low_balance_threshold}
                    onChange={(e) => setC("pay_per_txn_low_balance_threshold", toNum(e.target.value))} /></label>
              </div>
            </div>

            <div className={styles.actions}>
              <button type="button" className="btn btn-primary" disabled={savingConfig} onClick={saveConfig}>
                Save service config
              </button>
              {configMsg && <span className={styles.msg}>{configMsg}</span>}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
