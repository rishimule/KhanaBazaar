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
   *  still loading — every method is shown rather than flashing an empty list.
   *  An empty list means the store takes nothing for local orders. */
  acceptedMethods?: PaymentMethod[];
  /** Shown under the UPI option once selected, so the customer knows who they
   *  are paying before the order exists. */
  upiPayee?: { vpa: string; display_name: string } | null;
  /** Who a bank transfer reaches, shown under that option once selected. The
   *  account number appears only on the placed order. */
  bankPayee?: { account_name: string } | null;
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
  { value: "net_banking", labelKey: "bankTransferLabel", hintKey: "bankTransferHint", modes: ["door_delivery", "pickup"] },
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
  bankPayee,
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
  // Absent = the store payload hasn't loaded: show every method rather than
  // flashing an empty picker. Present (even empty) = what the store takes.
  const storeAccepts = (m: PaymentMethod) =>
    !acceptedMethods || acceptedMethods.includes(m);
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
            {opt.value === "net_banking" &&
              value === "net_banking" &&
              bankPayee &&
              previewAmount != null && (
                <p className={styles.payeePreview}>
                  {t("bankPreview", {
                    amount: previewAmount.toFixed(2),
                    name: bankPayee.account_name,
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
      {options.length === 0 && (
        <p className={styles.note} role="status">
          {t(deliveryMode === "pickup" ? "noMethodsPickup" : "noMethodsDoor")}
        </p>
      )}
      {credit != null && value === "credit" && (
        <p className={styles.note}>{t("creditSettleNote")}</p>
      )}
    </fieldset>
  );
}
