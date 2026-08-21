"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import type { ReturnRequest } from "@/types";
import styles from "./ReceiptCodePanel.module.css";

interface Props {
  request: ReturnRequest;
  namespace?: string;
}

/**
 * The handover code, shown only to the owning customer while the return is
 * active. Modelled on `orders/DeliveryOtpPanel` — the customer reads it out and
 * the store types it, so it renders nothing for sellers (whose payloads never
 * carry the code at all).
 */
export default function ReceiptCodePanel({
  request,
  namespace = "Account.returns",
}: Props) {
  const t = useTranslations(namespace);
  if (request.status !== "active" || !request.receipt_otp) return null;

  return (
    <section className={styles.panel}>
      <h2 className={styles.title}>{t("handoverCodeTitle")}</h2>
      <p className={styles.code}>{request.receipt_otp}</p>
      <p className={styles.hint}>{t("handoverCodeHint")}</p>
    </section>
  );
}
