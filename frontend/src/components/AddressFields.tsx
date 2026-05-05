"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { Address } from "@/types";
import { getIndianStates } from "@/lib/indian-states";
import styles from "./AddressFields.module.css";

export interface AddressFieldsErrors {
  address_line1?: string;
  address_line2?: string;
  landmark?: string;
  city?: string;
  state?: string;
  pincode?: string;
  country?: string;
  latitude?: string;
  longitude?: string;
}

export interface AddressFieldsProps {
  value: Address;
  onChange: (next: Address) => void;
  errors?: AddressFieldsErrors;
  disabled?: boolean;
}

export function emptyAddress(): Address {
  return {
    address_line1: "",
    address_line2: null,
    landmark: null,
    city: "",
    state: "",
    pincode: "",
    country: "India",
    latitude: null,
    longitude: null,
  };
}

export function AddressFields({ value, onChange, errors, disabled }: AddressFieldsProps) {
  const t = useTranslations("Address");
  const [states, setStates] = useState<string[]>([]);
  const [statesError, setStatesError] = useState<string | null>(null);

  useEffect(() => {
    getIndianStates()
      .then(setStates)
      .catch(() => setStatesError(t("statesLoadError")));
  }, [t]);

  const update = <K extends keyof Address>(key: K, v: Address[K]) =>
    onChange({ ...value, [key]: v });

  const errClass = (k: keyof Address) =>
    errors?.[k] ? `${styles.input} ${styles.inputError}` : styles.input;

  return (
    <div className={styles.grid}>
      <div className={`${styles.field} ${styles.span2}`}>
        <label className={styles.label} htmlFor="addr-line1">{t("line1Label")}</label>
        <input
          id="addr-line1"
          type="text"
          className={errClass("address_line1")}
          value={value.address_line1}
          onChange={(e) => update("address_line1", e.target.value)}
          placeholder={t("line1Placeholder")}
          maxLength={120}
          disabled={disabled}
          required
        />
        {errors?.address_line1 && <span className={styles.error}>{errors.address_line1}</span>}
      </div>

      <div className={`${styles.field} ${styles.span2}`}>
        <label className={styles.label} htmlFor="addr-line2">{t("line2Label")}</label>
        <input
          id="addr-line2"
          type="text"
          className={errClass("address_line2")}
          value={value.address_line2 ?? ""}
          onChange={(e) => update("address_line2", e.target.value || null)}
          placeholder={t("line2Placeholder")}
          maxLength={120}
          disabled={disabled}
        />
      </div>

      <div className={`${styles.field} ${styles.span2}`}>
        <label className={styles.label} htmlFor="addr-landmark">{t("landmarkLabel")}</label>
        <input
          id="addr-landmark"
          type="text"
          className={errClass("landmark")}
          value={value.landmark ?? ""}
          onChange={(e) => update("landmark", e.target.value || null)}
          placeholder={t("landmarkPlaceholder")}
          maxLength={120}
          disabled={disabled}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="addr-city">{t("cityLabel")}</label>
        <input
          id="addr-city"
          type="text"
          className={errClass("city")}
          value={value.city}
          onChange={(e) => update("city", e.target.value)}
          maxLength={80}
          disabled={disabled}
          required
        />
        {errors?.city && <span className={styles.error}>{errors.city}</span>}
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="addr-state">{t("stateLabel")}</label>
        <select
          id="addr-state"
          className={errClass("state")}
          value={value.state}
          onChange={(e) => update("state", e.target.value)}
          disabled={disabled}
          required
        >
          <option value="">{t("stateSelectPlaceholder")}</option>
          {states.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        {statesError && <span className={styles.error}>{statesError}</span>}
        {errors?.state && <span className={styles.error}>{errors.state}</span>}
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="addr-pincode">{t("pincodeLabel")}</label>
        <input
          id="addr-pincode"
          type="text"
          inputMode="numeric"
          pattern="[1-9]\d{5}"
          maxLength={6}
          className={errClass("pincode")}
          value={value.pincode}
          onChange={(e) => update("pincode", e.target.value.replace(/\D/g, "").slice(0, 6))}
          disabled={disabled}
          required
        />
        {errors?.pincode && <span className={styles.error}>{errors.pincode}</span>}
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="addr-country">{t("countryLabel")}</label>
        <input
          id="addr-country"
          type="text"
          className={errClass("country")}
          value={value.country}
          readOnly
          disabled
        />
      </div>
    </div>
  );
}
