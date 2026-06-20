// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  WINDOW_META,
  buildSelectableOptions,
  formatDateLabel,
  type DeliveryWindowKey,
} from "@/lib/deliveryWindows";
import styles from "./DeliveryTimePicker.module.css";

const LABEL_KEY: Record<DeliveryWindowKey, string> = {
  morning: "windowMorning",
  afternoon: "windowAfternoon",
  evening: "windowEvening",
};

export interface PreferredWindowValue {
  date: string;
  window: DeliveryWindowKey;
}

export default function DeliveryTimePicker({
  value,
  onChange,
}: {
  value: PreferredWindowValue | null;
  onChange: (v: PreferredWindowValue | null) => void;
}) {
  const t = useTranslations("Order.delivery");
  const locale = useLocale();
  const days = useMemo(() => buildSelectableOptions(), []);
  const [open, setOpen] = useState(value !== null);
  const [activeDate, setActiveDate] = useState<string>(
    value?.date ?? days[0]?.date ?? "",
  );

  const activeDay = days.find((d) => d.date === activeDate) ?? days[0];

  const selectAsap = () => {
    setOpen(false);
    onChange(null);
  };

  return (
    <div className={styles.root}>
      <div className={styles.options}>
        <button
          type="button"
          className={`${styles.modeBtn} ${!open ? styles.modeActive : ""}`}
          onClick={selectAsap}
          aria-pressed={!open}
        >
          {t("asap")}
        </button>
        <button
          type="button"
          className={`${styles.modeBtn} ${open ? styles.modeActive : ""}`}
          onClick={() => setOpen(true)}
          aria-pressed={open}
        >
          {t("choose")}
        </button>
      </div>

      {open && activeDay && (
        <div className={styles.scheduler}>
          <div className={styles.dateRow}>
            {days.map((d) => (
              <button
                type="button"
                key={d.date}
                className={`${styles.dateChip} ${d.date === activeDate ? styles.chipActive : ""}`}
                onClick={() => setActiveDate(d.date)}
              >
                {d.relative ? t(d.relative) : formatDateLabel(d.date, locale)}
              </button>
            ))}
          </div>
          <div className={styles.windowRow}>
            {activeDay.windows.map((w) => {
              const selected =
                value?.date === activeDay.date && value?.window === w;
              return (
                <button
                  type="button"
                  key={w}
                  className={`${styles.windowBtn} ${selected ? styles.windowActive : ""}`}
                  onClick={() => onChange({ date: activeDay.date, window: w })}
                >
                  <span className={styles.windowName}>{t(LABEL_KEY[w])}</span>
                  <span className={styles.windowHours}>{WINDOW_META[w].hours}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
