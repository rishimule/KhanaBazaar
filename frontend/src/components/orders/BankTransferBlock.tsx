"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useState } from "react";
import { useTranslations } from "next-intl";
import type { BankTransferDetails } from "@/types";
import styles from "./BankTransferBlock.module.css";

/** Account name, number and IFSC with copy buttons, the amount, and the
 *  remark that lets the store match the transfer. Shared by the local pay
 *  panel and the courier pay panel. */
export default function BankTransferBlock({
  bank,
  amount,
  orderId,
  onError,
}: {
  bank: BankTransferDetails;
  amount: number;
  orderId: number;
  onError?: (message: string) => void;
}) {
  const t = useTranslations("BankPay");
  const [copied, setCopied] = useState<"number" | "ifsc" | null>(null);

  async function copy(field: "number" | "ifsc", text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(field);
      window.setTimeout(() => setCopied(null), 2000);
    } catch {
      onError?.(t("copyFailed"));
    }
  }

  return (
    <>
      <dl className={styles.bank}>
        <dt>{t("accountName")}</dt>
        <dd>{bank.account_name}</dd>
        <dt>{t("accountNumber")}</dt>
        <dd>
          <code>{bank.account_number}</code>
          <button type="button" className="btn" onClick={() => copy("number", bank.account_number)}>
            {copied === "number" ? t("copied") : t("copy")}
          </button>
        </dd>
        <dt>{t("ifsc")}</dt>
        <dd>
          <code>{bank.ifsc}</code>
          <button type="button" className="btn" onClick={() => copy("ifsc", bank.ifsc)}>
            {copied === "ifsc" ? t("copied") : t("copy")}
          </button>
        </dd>
        <dt>{t("amount")}</dt>
        <dd>₹{amount.toFixed(2)}</dd>
      </dl>
      <p className={styles.hint}>{t("remarks", { id: orderId })}</p>
    </>
  );
}
