"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { use, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import AdminReasonModal from "@/components/admin/AdminReasonModal";
import MethodsByMode, { PaymentWarnings } from "@/components/payments/MethodsByMode";
import PaymentSwitchList from "@/components/payments/PaymentSwitchList";
import { useAuth } from "@/lib/AuthContext";
import { adminSetPaymentMethods, fetchSellerPayments } from "@/lib/adminActions";
import { errorsKey } from "@/lib/errors";
import { lastMethodMode } from "@/lib/sellerPayments";
import type { PaymentSettings, PaymentSwitchField } from "@/types";
import styles from "./page.module.css";

const LABEL_KEY: Record<PaymentSwitchField, string> = {
  upi_enabled: "upiLabel",
  bank_transfer_enabled: "bankLabel",
  cod_enabled: "cashLabel",
  pay_at_store_enabled: "payAtStoreLabel",
};

/** Admin view of a seller's payment switches (spec 2026-10-07 §8): every flip
 *  goes through a reason prompt and is audited server-side — e.g. stopping a
 *  stolen UPI ID when the seller can't. */
export default function SellerPaymentsTab({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const sellerId = Number(id);
  const t = useTranslations("Admin.sellerHub.payments");
  const tc = useTranslations("Admin.common");
  const tShared = useTranslations("Shared.paymentSettings");
  const tErr = useTranslations("Errors");
  const { token } = useAuth();
  const [settings, setSettings] = useState<PaymentSettings | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [pending, setPending] = useState<{ field: PaymentSwitchField; next: boolean } | null>(
    null,
  );
  const [busy, setBusy] = useState<PaymentSwitchField | null>(null);
  const [modalError, setModalError] = useState<string | null>(null);
  // Load once per seller: a token refresh must not blank the tab on a blip or
  // revert a switch that was saved meanwhile. A failed load retries on the
  // next token refresh.
  const loadedFor = useRef<number | null>(null);

  useEffect(() => {
    if (!token || loadedFor.current === sellerId) return;
    let cancelled = false;
    fetchSellerPayments(sellerId, token)
      .then((s) => {
        if (cancelled) return;
        loadedFor.current = sellerId;
        setLoadError(false);
        setSettings(s);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [sellerId, token]);

  async function confirm(reason: string) {
    if (!pending || !token) return;
    setBusy(pending.field);
    setModalError(null);
    try {
      setSettings(
        await adminSetPaymentMethods(sellerId, { [pending.field]: pending.next }, reason, token),
      );
      setPending(null);
    } catch (e) {
      const mode = lastMethodMode(e);
      const key = errorsKey(e);
      setModalError(
        mode
          ? tShared(mode === "pickup" ? "lastMethodPickup" : "lastMethodDoor")
          : key
            ? tErr(key)
            : t("saveFailed"),
      );
      // The seller may have changed the switches meanwhile.
      try {
        setSettings(await fetchSellerPayments(sellerId, token));
      } catch {
        // Keep the last known switches; the modal already shows the error.
      }
    } finally {
      setBusy(null);
    }
  }

  if (loadError) {
    return (
      <p className={styles.error} role="alert">
        {t("loadError")}
      </p>
    );
  }
  if (!settings) return <p className={styles.muted}>{tc("loading")}</p>;

  const method = pending ? tShared(LABEL_KEY[pending.field]) : "";
  return (
    <section className={styles.wrap} aria-labelledby="admin-payments-title">
      <h2 id="admin-payments-title" className={styles.title}>
        {t("title")}
      </h2>
      <p className={styles.muted}>{t("intro")}</p>
      <PaymentWarnings settings={settings} />
      <div className={styles.card}>
        <PaymentSwitchList
          settings={settings}
          busy={busy}
          onToggle={(field, next) => {
            setModalError(null);
            setPending({ field, next });
          }}
        />
        <MethodsByMode settings={settings} />
      </div>
      <div className={styles.card}>
        <h3 className={styles.subtitle}>{t("detailsTitle")}</h3>
        <dl className={styles.details}>
          <dt>{t("upiId")}</dt>
          <dd className={styles.mono}>{settings.upi_vpa ?? t("notAdded")}</dd>
          <dt>{t("accountHolder")}</dt>
          <dd>{settings.bank_account_name ?? t("notAdded")}</dd>
          <dt>{t("accountNumber")}</dt>
          <dd className={styles.mono}>{settings.bank_account_number ?? t("notAdded")}</dd>
          <dt>{t("ifsc")}</dt>
          <dd className={styles.mono}>{settings.bank_ifsc ?? t("notAdded")}</dd>
        </dl>
      </div>
      {pending && (
        <AdminReasonModal
          title={pending.next ? t("reasonTitleOn", { method }) : t("reasonTitleOff", { method })}
          description={t("reasonDescription")}
          placeholder={t("reasonPlaceholder")}
          destructive={!pending.next}
          onConfirm={confirm}
          onClose={() => {
            // Esc / ✕ / backdrop mid-request would leave its result nowhere
            // to show; the modal closes itself once the save settles.
            if (busy) return;
            setPending(null);
            setModalError(null);
          }}
          error={modalError}
        />
      )}
    </section>
  );
}
