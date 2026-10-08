"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useTranslations } from "next-intl";
import type { DeliveryMode, PaymentSettings } from "@/types";
import styles from "./PaymentSettings.module.css";

const MODES: { mode: DeliveryMode; labelKey: string; warnKey: string }[] = [
  { mode: "door_delivery", labelKey: "modeDoor", warnKey: "warnDoor" },
  { mode: "pickup", labelKey: "modePickup", warnKey: "warnPickup" },
  { mode: "courier", labelKey: "modeCourier", warnKey: "warnCourier" },
];

/** A banner for every delivery mode the store offers but customers can't pay
 *  for — e.g. after an emergency UPI stop left door delivery with nothing. */
export function PaymentWarnings({ settings }: { settings: PaymentSettings }) {
  const t = useTranslations("Shared.paymentSettings");
  const empty = MODES.filter((m) => settings.methods_by_mode[m.mode]?.length === 0);
  if (empty.length === 0) return null;
  return (
    <div className={styles.warnings}>
      {empty.map((m) => (
        <div key={m.mode} className={styles.warning} role="alert">
          {t(m.warnKey)}
        </div>
      ))}
    </div>
  );
}

/** One line per offered delivery mode: exactly what customers see at
 *  checkout, as computed by the server's single rule. */
export default function MethodsByMode({ settings }: { settings: PaymentSettings }) {
  const t = useTranslations("Shared.paymentSettings");
  const tm = useTranslations("Order.payment.method");
  const offered = MODES.filter((m) => settings.methods_by_mode[m.mode] !== undefined);
  return (
    <div className={styles.summary}>
      <h3 className={styles.summaryTitle}>{t("summaryTitle")}</h3>
      <dl className={styles.summaryList}>
        {offered.map((m) => {
          const methods = settings.methods_by_mode[m.mode] ?? [];
          return (
            <div key={m.mode} className={styles.summaryRow}>
              <dt>{t(m.labelKey)}</dt>
              <dd className={methods.length ? undefined : styles.none}>
                {methods.length ? methods.map((x) => tm(x)).join(" · ") : t("noMethods")}
              </dd>
            </div>
          );
        })}
      </dl>
    </div>
  );
}
