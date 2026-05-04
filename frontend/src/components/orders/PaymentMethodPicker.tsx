"use client";

import type { PaymentMethod } from "@/types";
import styles from "./PaymentMethodPicker.module.css";

interface Props {
  value: PaymentMethod;
  onChange: (method: PaymentMethod) => void;
}

const OPTIONS: { value: PaymentMethod; label: string; hint: string }[] = [
  { value: "upi", label: "UPI", hint: "Pay via UPI app" },
  { value: "cash", label: "Cash on delivery", hint: "Pay when you receive" },
];

export default function PaymentMethodPicker({ value, onChange }: Props) {
  return (
    <fieldset className={styles.fieldset}>
      <legend className={styles.legend}>Payment method</legend>
      <div className={styles.options}>
        {OPTIONS.map((opt) => (
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
            <span className={styles.label}>{opt.label}</span>
            <span className={styles.hint}>{opt.hint}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
