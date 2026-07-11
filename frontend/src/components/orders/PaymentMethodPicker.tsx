"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import type { DeliveryMode, PaymentMethod } from "@/types";
import styles from "./PaymentMethodPicker.module.css";

/** Credit standing at this store, when the customer has a credit account.
 * Omit/null when they don't — the credit option is then hidden entirely. */
export interface CreditOption {
  available: number;
  eligible: boolean;
}

interface Props {
  value: PaymentMethod;
  onChange: (method: PaymentMethod) => void;
  deliveryMode?: DeliveryMode;
  credit?: CreditOption | null;
}

const BASE_OPTIONS: {
  value: PaymentMethod;
  labelKey: string;
  hintKey: string;
  modes: DeliveryMode[];
}[] = [
  { value: "upi", labelKey: "upiLabel", hintKey: "upiHint", modes: ["door_delivery", "pickup"] },
  { value: "net_banking", labelKey: "netBankingLabel", hintKey: "netBankingHint", modes: ["door_delivery", "pickup"] },
  { value: "cash", labelKey: "cashLabel", hintKey: "cashHint", modes: ["door_delivery"] },
  { value: "pay_at_store", labelKey: "payAtStoreLabel", hintKey: "payAtStoreHint", modes: ["pickup"] },
];

export default function PaymentMethodPicker({
  value,
  onChange,
  deliveryMode = "door_delivery",
  credit,
}: Props) {
  const t = useTranslations("Payment");
  const options = BASE_OPTIONS.filter((opt) => opt.modes.includes(deliveryMode));
  return (
    <fieldset className={styles.fieldset}>
      <legend className={styles.legend}>{t("legend")}</legend>
      <div className={styles.options}>
        {options.map((opt) => (
          <label
            key={opt.value}
            className={`${styles.option} ${value === opt.value ? styles.selected : ""}`}
          >
            <input
              type="radio"
              name="payment_method"
              value={opt.value}
              checked={value === opt.value}
              onChange={() => onChange(opt.value)}
              className={styles.radio}
            />
            <span className={styles.label}>{t(opt.labelKey)}</span>
            <span className={styles.hint}>{t(opt.hintKey)}</span>
          </label>
        ))}
        {credit != null && (
          <label
            className={`${styles.option} ${value === "credit" ? styles.selected : ""} ${
              credit.eligible ? "" : styles.disabled
            }`}
          >
            <input
              type="radio"
              name="payment_method"
              value="credit"
              checked={value === "credit"}
              disabled={!credit.eligible}
              onChange={() => onChange("credit")}
              className={styles.radio}
            />
            <span className={styles.label}>{t("creditLabel")}</span>
            <span className={styles.hint}>
              {credit.eligible
                ? t("creditAvailable", { amount: credit.available.toFixed(0) })
                : t("creditInsufficient", { amount: credit.available.toFixed(0) })}
            </span>
          </label>
        )}
      </div>
      {credit != null && value === "credit" && (
        <p className={styles.note}>{t("creditSettleNote")}</p>
      )}
    </fieldset>
  );
}
