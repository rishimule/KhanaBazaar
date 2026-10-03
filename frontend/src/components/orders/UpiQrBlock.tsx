"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useState, useSyncExternalStore } from "react";
import { useTranslations } from "next-intl";
import { QRCodeSVG } from "qrcode.react";
import { buildUpiUri, isLikelyIOS } from "@/lib/upi";
import styles from "./UpiQrBlock.module.css";

// The user agent never changes for the life of the page, so nothing to subscribe to.
const subscribeNever = () => () => {};
const serverIsIOS = () => false;

/** QR + VPA + pay-with-app for one UPI payment. Shared by the local UPI panel
 *  and the courier pay panel. The QR is built from the seller's VPA — never
 *  their uploaded image, whose payee we cannot read. */
export default function UpiQrBlock({
  vpa,
  payeeName,
  amount,
  orderId,
  onError,
}: {
  vpa: string;
  payeeName: string;
  amount: number;
  orderId: number;
  onError?: (message: string) => void;
}) {
  const t = useTranslations("UpiPay");
  const [copied, setCopied] = useState(false);
  // The UA is unavailable server-side: the server snapshot says "not iOS" and
  // React swaps in the client value after hydration, with no mismatch.
  const ios = useSyncExternalStore(subscribeNever, isLikelyIOS, serverIsIOS);
  const uri = buildUpiUri({ vpa, payeeName, amount, orderId });

  async function copyVpa() {
    try {
      await navigator.clipboard.writeText(vpa);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      onError?.(t("copyFailed"));
    }
  }

  return (
    <>
      {/* Kept on a white plate in every theme: a dark-mode-inverted QR will
          not scan. */}
      <div className={styles.qrWrap}>
        <QRCodeSVG value={uri} size={200} level="M" />
      </div>
      <p className={styles.hint}>{ios ? t("scanHintIos") : t("scanHint")}</p>

      <div className={styles.vpaRow}>
        <code className={styles.vpa}>{vpa}</code>
        <button type="button" className="btn" onClick={copyVpa}>
          {copied ? t("copied") : t("copyVpa")}
        </button>
      </div>

      {/* iOS Safari does not reliably fire `upi://`, so the app button is
          demoted there rather than removed — it still works in some apps. */}
      <a className={ios ? "btn" : "btn btn-primary"} href={uri}>
        {t("payWithApp")}
      </a>
    </>
  );
}
