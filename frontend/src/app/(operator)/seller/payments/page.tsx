"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { createMyChangeRequest, listMyChangeRequests } from "@/lib/changeRequests";
import { errorsKey } from "@/lib/errors";
import {
  getPaymentSettings,
  lastMethodMode,
  maskAccountNumber,
  setPaymentMethods,
  uploadUpiQr,
  UPI_VPA_REGEX,
} from "@/lib/sellerPayments";
import ProfileChangeRequestModal from "@/components/ProfileChangeRequestModal";
import PaymentSwitchList from "@/components/payments/PaymentSwitchList";
import MethodsByMode, { PaymentWarnings } from "@/components/payments/MethodsByMode";
import type {
  PaymentSettings,
  PaymentSwitchField,
  SellerProfileChangeRequest,
} from "@/types";
import styles from "./page.module.css";

// Per device: the note explains a one-off change in what the switch covers.
const BANK_NOTICE_KEY = "kb_seller_bank_notice_dismissed";

function readNoticeDismissed(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return window.localStorage.getItem(BANK_NOTICE_KEY) === "1";
  } catch {
    return false;
  }
}

/** Banner for an open change request, naming the value under review. */
function ReviewBanner({
  cr,
  value,
}: {
  cr: SellerProfileChangeRequest;
  value: string | null;
}) {
  const t = useTranslations("Seller.payments");
  const warn = cr.status === "changes_requested";
  return (
    <div
      className={`${styles.banner} ${warn ? styles.bannerWarn : styles.bannerInfo}`}
      role="status"
    >
      <span>
        {warn
          ? t("changesRequested")
          : value
            ? t("underReview", { value })
            : t("underReviewNoValue")}
      </span>
      <Link href={`/seller/profile/requests/${cr.id}`} className={styles.bannerLink}>
        {t("viewRequest")}
      </Link>
    </div>
  );
}

export default function SellerPaymentsPage() {
  const t = useTranslations("Seller.payments");
  const tShared = useTranslations("Shared.paymentSettings");
  const tc = useTranslations("Seller.common");
  const tErr = useTranslations("Errors");
  const { token, loading: authLoading } = useAuth();
  const [settings, setSettings] = useState<PaymentSettings | null>(null);
  const [openCRs, setOpenCRs] = useState<SellerProfileChangeRequest[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [busy, setBusy] = useState<PaymentSwitchField | null>(null);
  const [switchError, setSwitchError] = useState<string | null>(null);
  const [upiFormOpen, setUpiFormOpen] = useState(false);
  const [upiInput, setUpiInput] = useState("");
  const [upiFile, setUpiFile] = useState<File | null>(null);
  const [upiBusy, setUpiBusy] = useState(false);
  const [upiError, setUpiError] = useState<string | null>(null);
  const [upiNotice, setUpiNotice] = useState<string | null>(null);
  const [bankModalOpen, setBankModalOpen] = useState(false);
  // Rendered only after the settings load (client-side), so reading storage in
  // the initializer cannot cause a hydration mismatch.
  const [noticeDismissed, setNoticeDismissed] = useState(readNoticeDismissed);

  useEffect(() => {
    if (authLoading || !token) return;
    let cancelled = false;
    Promise.all([
      getPaymentSettings(token),
      listMyChangeRequests(token, "open").catch(() => [] as SellerProfileChangeRequest[]),
    ])
      .then(([s, crs]) => {
        if (cancelled) return;
        setSettings(s);
        setOpenCRs(crs);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [authLoading, token]);

  async function refreshRequests() {
    if (!token) return;
    try {
      setOpenCRs(await listMyChangeRequests(token, "open"));
    } catch {
      // best-effort; the banner catches up on the next visit
    }
  }

  async function toggle(field: PaymentSwitchField, next: boolean) {
    if (!token || busy) return;
    if (field === "upi_enabled" && !next && !window.confirm(t("upiOffConfirm"))) return;
    setBusy(field);
    setSwitchError(null);
    try {
      setSettings(await setPaymentMethods(token, { [field]: next }));
    } catch (e) {
      const mode = lastMethodMode(e);
      if (mode) {
        setSwitchError(tShared(mode === "pickup" ? "lastMethodPickup" : "lastMethodDoor"));
      } else {
        const key = errorsKey(e);
        setSwitchError(key ? tErr(key) : t("switchFailed"));
      }
      // Another tab, or an admin, may have changed the switches meanwhile.
      try {
        setSettings(await getPaymentSettings(token));
      } catch {
        // Keep the last known switches; the error above already explains.
      }
    } finally {
      setBusy(null);
    }
  }

  async function submitUpi() {
    if (!token) return;
    const vpa = upiInput.trim();
    if (!UPI_VPA_REGEX.test(vpa)) {
      setUpiError(t("upiInvalid"));
      return;
    }
    setUpiBusy(true);
    setUpiError(null);
    try {
      // With an image, the multipart route makes a trusted owner-scoped
      // storage key; the JSON path refuses a caller-supplied image URL.
      if (upiFile) {
        await uploadUpiQr(vpa, upiFile, token);
      } else {
        await createMyChangeRequest(token, {
          group: "payments",
          proposed: { upi_vpa: vpa, upi_enabled: true },
        });
      }
      setUpiFormOpen(false);
      setUpiFile(null);
      setUpiNotice(t("upiSubmitted"));
      await refreshRequests();
    } catch (e) {
      const key = errorsKey(e);
      setUpiError(key ? tErr(key) : t("submitFailed"));
    } finally {
      setUpiBusy(false);
    }
  }

  function openUpiForm() {
    setUpiInput(settings?.upi_vpa ?? "");
    setUpiFile(null);
    setUpiError(null);
    setUpiNotice(null);
    setUpiFormOpen(true);
  }

  function dismissNotice() {
    setNoticeDismissed(true);
    try {
      window.localStorage.setItem(BANK_NOTICE_KEY, "1");
    } catch {
      // storage blocked: the note simply shows again next visit
    }
  }

  if (authLoading || (!settings && !loadError)) {
    return <div className={styles.loader}>{tc("loading")}</div>;
  }
  if (loadError || !settings) {
    return (
      <div className={styles.page}>
        <h1 className={styles.title}>{t("heading")}</h1>
        <div className={styles.errorBanner} role="alert">
          {t("loadError")}
        </div>
      </div>
    );
  }

  const upiCR = openCRs.find((cr) => cr.group === "payments") ?? null;
  const bankCR = openCRs.find((cr) => cr.group === "banking") ?? null;
  const proposedVpa = upiCR ? String(upiCR.proposed_json.upi_vpa ?? "") || null : null;
  const proposedAccount = bankCR
    ? maskAccountNumber(String(bankCR.proposed_json.bank_account_number ?? ""))
    : null;

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1 className={styles.title}>{t("heading")}</h1>
        <Link href="/seller/profile/requests" className={styles.requestsLink}>
          {t("allRequests")}
        </Link>
      </div>
      <p className={styles.intro}>{t("intro")}</p>

      <PaymentWarnings settings={settings} />

      <section className={styles.card} aria-labelledby="payments-switches">
        <h2 id="payments-switches" className={styles.cardTitle}>
          {t("switchesTitle")}
        </h2>
        {switchError && (
          <div className={styles.errorBanner} role="alert">
            {switchError}
          </div>
        )}
        <PaymentSwitchList settings={settings} busy={busy} onToggle={toggle} />
        {settings.bank_transfer_enabled && !noticeDismissed && (
          <div className={`${styles.banner} ${styles.bannerInfo}`} role="status">
            <span>{t("bankNotice")}</span>
            <button type="button" className={styles.linkButton} onClick={dismissNotice}>
              {t("dismiss")}
            </button>
          </div>
        )}
        <MethodsByMode settings={settings} />
      </section>

      <section className={styles.card} aria-labelledby="payments-upi">
        <header className={styles.cardHeader}>
          <h2 id="payments-upi" className={styles.cardTitle}>
            {t("upiTitle")}
          </h2>
          {!upiCR && !upiFormOpen && (
            <button type="button" className={styles.editBtn} onClick={openUpiForm}>
              {settings.upi_vpa ? t("change") : t("add")}
            </button>
          )}
        </header>
        {upiCR && <ReviewBanner cr={upiCR} value={proposedVpa} />}
        <p className={styles.value}>
          <span className={styles.mono}>{settings.upi_vpa ?? t("notAdded")}</span>
        </p>
        {upiNotice && (
          <p className={styles.notice} role="status">
            {upiNotice}
          </p>
        )}
        {upiFormOpen && (
          <div className={styles.form}>
            <label className={styles.fieldLabel} htmlFor="upi-vpa-input">
              {t("upiInputLabel")}
            </label>
            <input
              id="upi-vpa-input"
              type="text"
              className={styles.input}
              value={upiInput}
              onChange={(e) => setUpiInput(e.target.value.trim())}
              placeholder="yourname@okhdfcbank"
              autoComplete="off"
            />
            {/* A plain file input, not AvatarUploader: its crop step can cut a
                QR's quiet zone and leave an image that no longer scans. */}
            <label className={styles.fieldLabel} htmlFor="upi-qr-input">
              {t("upiQrLabel")}
            </label>
            <input
              id="upi-qr-input"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(e) => setUpiFile(e.target.files?.[0] ?? null)}
            />
            <p className={styles.hint}>{t("upiQrHint")}</p>
            {settings.upi_vpa && <p className={styles.hint}>{t("keepDetailsNote")}</p>}
            {upiError && (
              <p className={styles.fieldError} role="alert">
                {upiError}
              </p>
            )}
            <div className={styles.actions}>
              <button
                type="button"
                className="btn btn-primary"
                disabled={upiBusy}
                onClick={submitUpi}
              >
                {t("submit")}
              </button>
              <button
                type="button"
                className="btn btn-outline"
                disabled={upiBusy}
                onClick={() => setUpiFormOpen(false)}
              >
                {t("cancel")}
              </button>
            </div>
          </div>
        )}
      </section>

      <section className={styles.card} aria-labelledby="payments-bank">
        <header className={styles.cardHeader}>
          <h2 id="payments-bank" className={styles.cardTitle}>
            {t("bankTitle")}
          </h2>
          {!bankCR && (
            <button
              type="button"
              className={styles.editBtn}
              onClick={() => setBankModalOpen(true)}
            >
              {settings.bank_account_number ? t("change") : t("add")}
            </button>
          )}
        </header>
        {bankCR && <ReviewBanner cr={bankCR} value={proposedAccount} />}
        <dl className={styles.details}>
          <dt>{t("accountHolder")}</dt>
          <dd>{settings.bank_account_name ?? t("notAdded")}</dd>
          <dt>{t("accountNumber")}</dt>
          <dd className={styles.mono}>
            {maskAccountNumber(settings.bank_account_number) ?? t("notAdded")}
          </dd>
          <dt>{t("ifsc")}</dt>
          <dd className={styles.mono}>{settings.bank_ifsc ?? t("notAdded")}</dd>
        </dl>
        {settings.bank_account_number && <p className={styles.hint}>{t("keepDetailsNote")}</p>}
      </section>

      {bankModalOpen && token && (
        <ProfileChangeRequestModal
          group="banking"
          currentValues={{
            bank_account_number: settings.bank_account_number ?? "",
            bank_ifsc: settings.bank_ifsc ?? "",
            bank_account_name: settings.bank_account_name ?? "",
            bank_transfer_enabled: settings.bank_transfer_enabled,
          }}
          open
          onClose={() => setBankModalOpen(false)}
          onSubmit={async (proposed, note) => {
            await createMyChangeRequest(token, { group: "banking", proposed, note });
            await refreshRequests();
          }}
        />
      )}
    </div>
  );
}
