"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import type { PaymentMethod } from "@/types";
import styles from "./PaymentMethodPicker.module.css";

interface Props {
  value: PaymentMethod;
  onChange: (method: PaymentMethod) => void;
}

const OPTION_KEYS: { value: PaymentMethod; labelKey: string; hintKey: string }[] = [
  { value: "upi", labelKey: "upiLabel", hintKey: "upiHint" },
  { value: "cash", labelKey: "cashLabel", hintKey: "cashHint" },
];

export default function PaymentMethodPicker({ value, onChange }: Props) {
  const t = useTranslations("Payment");
  return (
    <fieldset className={styles.fieldset}>
      <legend className={styles.legend}>{t("legend")}</legend>
      <div className={styles.options}>
        {OPTION_KEYS.map((opt) => (
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
      </div>
    </fieldset>
  );
}
