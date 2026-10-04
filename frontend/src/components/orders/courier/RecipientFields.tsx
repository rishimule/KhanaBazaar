"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import type { CustomerProfile } from "@/types";
import styles from "./courier.module.css";

export interface RecipientValue {
  name: string;
  /** Canonical "+91XXXXXXXXXX", or "" while empty. */
  phone: string;
}

const PHONE = /^\+91[6-9]\d{9}$/;

/** The local digits of an Indian mobile however it was typed, pasted or
 *  autofilled: "+91 98765 43210", "919876543210" and "09876543210" all give
 *  "9876543210". Any other long run is kept whole, so the field shows it as
 *  invalid instead of silently cutting it down to a wrong but valid number. */
export function localMobileDigits(raw: string): string {
  const digits = raw.replace(/\D/g, "");
  if (digits.length === 12 && digits.startsWith("91")) return digits.slice(2);
  if (digits.length === 11 && digits.startsWith("0")) return digits.slice(1);
  return digits;
}

/** Mirrors the server's checkout rule (+91 mobile, non-empty name). */
export function isRecipientValid(value: RecipientValue): boolean {
  return value.name.trim().length > 0 && PHONE.test(value.phone);
}

/** Who the courier hands the parcel to. Pre-filled from the profile once,
 *  editable so the customer can send it to family elsewhere (spec D11). */
export default function RecipientFields({
  value,
  onChange,
}: {
  value: RecipientValue;
  onChange: (next: RecipientValue) => void;
}) {
  const t = useTranslations("Checkout.courier");
  const { token } = useAuth();
  const prefilled = useRef(false);
  const [phoneTouched, setPhoneTouched] = useState(false);
  // The profile fetch resolves later; read what's typed THEN, not what the
  // closure saw at mount, or the prefill would overwrite early typing.
  const latest = useRef({ value, onChange });
  useEffect(() => {
    latest.current = { value, onChange };
  });

  useEffect(() => {
    if (!token || prefilled.current) return;
    prefilled.current = true;
    get<CustomerProfile>("/api/v1/customers/me", token)
      .then((p) => {
        const { value: current, onChange: emit } = latest.current;
        if (current.name || current.phone) return; // never overwrite what was typed
        const name = [p.first_name, p.last_name].filter(Boolean).join(" ");
        emit({ name, phone: p.phone && PHONE.test(p.phone) ? p.phone : "" });
      })
      .catch(() => {
        // Typing the details in still works; no confident-but-wrong prefill.
      });
  }, [token]);

  const local = value.phone.replace(/^\+91/, "");
  // Complain once the field is left or all 10 digits are in — not on the
  // first keystroke of a number still being typed.
  const phoneInvalid =
    value.phone !== "" && !PHONE.test(value.phone) && (phoneTouched || local.length >= 10);
  return (
    <fieldset className={styles.fieldset}>
      <legend className={styles.legend}>{t("recipientTitle")}</legend>
      <p className={styles.hint}>{t("recipientHint")}</p>
      <label className={styles.field}>
        <span>{t("recipientName")}</span>
        <input
          type="text"
          autoComplete="name"
          maxLength={120}
          value={value.name}
          onChange={(e) => onChange({ ...value, name: e.target.value })}
        />
      </label>
      <label className={styles.field}>
        <span>{t("recipientPhone")}</span>
        <div className={styles.phoneRow}>
          <span className={styles.prefix}>+91</span>
          <input
            type="tel"
            inputMode="numeric"
            autoComplete="tel-national"
            placeholder={t("phonePlaceholder")}
            value={local}
            aria-invalid={phoneInvalid || undefined}
            onBlur={() => setPhoneTouched(true)}
            onChange={(e) => {
              // No maxLength: it would cut a pasted "+91 98765 43210" before
              // this handler could normalise it.
              const digits = localMobileDigits(e.target.value);
              onChange({ ...value, phone: digits ? `+91${digits}` : "" });
            }}
          />
        </div>
      </label>
      {phoneInvalid && (
        <p className={styles.error} role="alert">
          {t("phoneInvalid")}
        </p>
      )}
    </fieldset>
  );
}
