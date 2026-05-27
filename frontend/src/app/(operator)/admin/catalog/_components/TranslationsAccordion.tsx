"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState } from "react";
import { useTranslations } from "next-intl";
import type { TranslationOut } from "@/types";
import styles from "./TranslationsAccordion.module.css";

const LANGS: { code: string; label: string }[] = [
  { code: "hi", label: "हिन्दी" },
  { code: "mr", label: "मराठी" },
  { code: "gu", label: "ગુજરાતી" },
  { code: "pa", label: "ਪੰਜਾਬੀ" },
];

function ensure(rows: TranslationOut[], code: string): TranslationOut {
  return (
    rows.find((t) => t.language_code === code) || {
      language_code: code,
      name: "",
      description: "",
    }
  );
}

export function TranslationsAccordion({
  value,
  onChange,
  onTouch,
}: {
  value: TranslationOut[];
  onChange: (next: TranslationOut[]) => void;
  /** Fires once per language the user actually edits, so the parent can
   * include emptied-out translations in the save flow (which deletes
   * server-side). */
  onTouch?: (code: string) => void;
}) {
  const t = useTranslations("Admin.catalog");
  const [open, setOpen] = useState(value.length > 0);
  const [active, setActive] = useState(LANGS[0].code);

  function update(code: string, patch: Partial<TranslationOut>) {
    const next: TranslationOut[] = LANGS.map((l) =>
      l.code === code ? { ...ensure(value, l.code), ...patch } : ensure(value, l.code),
    );
    onChange(next);
    onTouch?.(code);
  }

  if (!open) {
    return (
      <button type="button" className={styles.toggle} onClick={() => setOpen(true)}>
        {t("addTranslations")}
      </button>
    );
  }

  const current = ensure(value, active);

  return (
    <div className={styles.wrap}>
      <button type="button" className={styles.toggle} onClick={() => setOpen(false)}>
        {t("hideTranslations")}
      </button>
      <div className={styles.tabs} role="tablist">
        {LANGS.map((l) => (
          <button
            key={l.code}
            type="button"
            role="tab"
            aria-selected={active === l.code}
            className={`${styles.tab} ${active === l.code ? styles.tabActive : ""}`}
            onClick={() => setActive(l.code)}
          >
            {l.label}
          </button>
        ))}
      </div>
      <div className={styles.fields}>
        <label className={styles.field}>
          <span>{t("fieldName")}</span>
          <input
            type="text"
            value={current.name}
            onChange={(e) => update(active, { name: e.target.value })}
          />
        </label>
        <label className={styles.field}>
          <span>{t("fieldDescription")}</span>
          <textarea
            value={current.description || ""}
            onChange={(e) => update(active, { description: e.target.value })}
          />
        </label>
      </div>
    </div>
  );
}
