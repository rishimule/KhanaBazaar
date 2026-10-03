"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { Fragment } from "react";
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
  /** Store-level methods from `Store.accepted_payment_methods`, intersected
   *  with the delivery-mode rules below. Undefined while the store payload is
   *  still loading — every method is shown rather than flashing an empty list. */
  acceptedMethods?: PaymentMethod[];
  /** Shown under the UPI option once selected, so the customer knows who they
   *  are paying before the order exists. */
  upiPayee?: { vpa: string; display_name: string } | null;
  /** Net payable (total minus applied store credit), for the preview line. */
  previewAmount?: number;
  /** Live courier methods from `Store.courier_payment_methods`. */
  courierMethods?: PaymentMethod[];
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
  acceptedMethods,
  upiPayee,
  previewAmount,
  courierMethods,
}: Props) {
  const t = useTranslations("Payment");
  if (deliveryMode === "courier") {
    // Prepaid only (spec D5): UPI and/or bank transfer, whichever is live.
    // Paid after acceptance, so this is a preference, changeable on the
    // order page (D7). Postpaid credit never applies.
    const live = (m: PaymentMethod) => !courierMethods || courierMethods.includes(m);
    const courierOptions = (
      [
        { value: "upi", labelKey: "upiLabel", hintKey: "courierPayLaterHint" },
        { value: "net_banking", labelKey: "bankTransferLabel", hintKey: "bankTransferHint" },
      ] as { value: PaymentMethod; labelKey: string; hintKey: string }[]
    ).filter((o) => live(o.value));
    return (
      <fieldset className={styles.fieldset}>
        <legend className={styles.legend}>{t("courierLegend")}</legend>
        <div className={styles.options}>
          {courierOptions.map((opt) => (
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
        {credit != null && <p className={styles.note}>{t("courierCreditNote")}</p>}
      </fieldset>
    );
  }
  // An empty/absent list means "not loaded yet" — fall back to showing all
  // methods rather than rendering a picker with nothing in it.
  const storeAccepts = (m: PaymentMethod) =>
    !acceptedMethods || acceptedMethods.length === 0 || acceptedMethods.includes(m);
  const options = BASE_OPTIONS.filter(
    (opt) => opt.modes.includes(deliveryMode) && storeAccepts(opt.value),
  );
  return (
    <fieldset className={styles.fieldset}>
      <legend className={styles.legend}>{t("legend")}</legend>
      <div className={styles.options}>
        {options.map((opt) => (
          <Fragment key={opt.value}>
            <label
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
            {opt.value === "upi" &&
              value === "upi" &&
              upiPayee &&
              previewAmount != null && (
                <p className={styles.payeePreview}>
                  {t("payeePreview", {
                    amount: previewAmount.toFixed(2),
                    vpa: upiPayee.vpa,
                    name: upiPayee.display_name,
                  })}
                </p>
              )}
          </Fragment>
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
