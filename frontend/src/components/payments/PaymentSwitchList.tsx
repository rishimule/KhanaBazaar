"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useTranslations } from "next-intl";
import type { PaymentSettings, PaymentSwitchField } from "@/types";
import styles from "./PaymentSettings.module.css";

interface Row {
  field: PaymentSwitchField;
  label: string;
  hint: string;
  on: boolean;
  /** Why the switch can't be turned on yet, or null when it can. */
  blocked: string | null;
}

/** The four store-wide payment switches (spec 2026-10-07 §4). Shared by the
 *  seller Payments page and the admin seller hub — the parent decides what a
 *  flip does (an instant save, or a reason prompt first). */
export default function PaymentSwitchList({
  settings,
  busy,
  onToggle,
}: {
  settings: PaymentSettings;
  /** The switch being saved; every switch is disabled meanwhile. */
  busy: PaymentSwitchField | null;
  onToggle: (field: PaymentSwitchField, next: boolean) => void;
}) {
  const t = useTranslations("Shared.paymentSettings");
  const rows: Row[] = [
    {
      field: "upi_enabled",
      label: t("upiLabel"),
      hint: t("upiHint"),
      on: settings.upi_enabled,
      blocked: settings.upi_vpa ? null : t("upiNeedsId"),
    },
    {
      field: "bank_transfer_enabled",
      label: t("bankLabel"),
      hint: t("bankHint"),
      on: settings.bank_transfer_enabled,
      blocked: settings.bank_details_complete ? null : t("bankNeedsDetails"),
    },
    {
      field: "cod_enabled",
      label: t("cashLabel"),
      hint: t("cashHint"),
      on: settings.cod_enabled,
      blocked: null,
    },
    {
      field: "pay_at_store_enabled",
      label: t("payAtStoreLabel"),
      hint: t("payAtStoreHint"),
      on: settings.pay_at_store_enabled,
      blocked: null,
    },
  ];
  return (
    <ul className={styles.switchList}>
      {rows.map((row) => {
        const id = `payment-switch-${row.field}`;
        const cantTurnOn = !row.on && row.blocked !== null;
        return (
          <li key={row.field} className={styles.switchRow}>
            <div className={styles.switchText}>
              <label htmlFor={id} className={styles.switchLabel}>
                {row.label}
              </label>
              <span id={`${id}-hint`} className={styles.switchHint}>
                {cantTurnOn ? row.blocked : row.hint}
              </span>
            </div>
            <span className={styles.switchControl}>
              {busy === row.field && (
                <span className={styles.saving} role="status">
                  {t("saving")}
                </span>
              )}
              <input
                id={id}
                type="checkbox"
                role="switch"
                className={styles.switch}
                checked={row.on}
                disabled={busy !== null || cantTurnOn}
                aria-describedby={`${id}-hint`}
                onChange={(e) => onToggle(row.field, e.target.checked)}
              />
            </span>
          </li>
        );
      })}
    </ul>
  );
}
