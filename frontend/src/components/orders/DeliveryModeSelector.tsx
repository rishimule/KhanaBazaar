"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import type { DeliveryMode } from "@/types";
import styles from "./DeliveryModeSelector.module.css";

interface Props {
  value: DeliveryMode;
  onChange: (mode: DeliveryMode) => void;
  /** When false, the Pick-up option is hidden (service has not opted in). */
  pickupAvailable: boolean;
}

export default function DeliveryModeSelector({ value, onChange, pickupAvailable }: Props) {
  const t = useTranslations("Checkout");
  const options: { mode: DeliveryMode; labelKey: string }[] = [
    { mode: "door_delivery", labelKey: "modeDoor" },
    ...(pickupAvailable
      ? [{ mode: "pickup" as DeliveryMode, labelKey: "modePickup" }]
      : []),
  ];
  return (
    <fieldset className={styles.fieldset}>
      <legend className={styles.legend}>{t("deliveryModeTitle")}</legend>
      <div className={styles.options}>
        {options.map((opt) => (
          <label
            key={opt.mode}
            className={`${styles.option} ${value === opt.mode ? styles.selected : ""}`}
          >
            <input
              type="radio"
              name="delivery_mode"
              value={opt.mode}
              checked={value === opt.mode}
              onChange={() => onChange(opt.mode)}
              className={styles.radio}
            />
            <span className={styles.label}>{t(opt.labelKey)}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
