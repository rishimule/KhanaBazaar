"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { Address } from "@/types";
import { getIndianStates } from "@/lib/indian-states";
import { AddressAutocomplete } from "@/components/AddressAutocomplete";
import { MapPicker } from "@/components/MapPicker";
import type { GeoPlace } from "@/lib/geo";
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
  /** When true, renders MapPicker open by default and the parent is expected
   *  to block submission until lat/lng are set. */
  requirePin?: boolean;
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
    digipin: null,
    place_id: null,
    location_source: null,
  };
}

function applyPlace(
  place: GeoPlace, current: Address, source: "autocomplete" | "pin",
): Address {
  const get = (type: string): string | null => {
    const c = place.components.find((c) => c.types.includes(type));
    return c ? c.long_name : null;
  };
  const line1FromFormatted = place.formatted_address.split(",")[0]?.trim();
  return {
    ...current,
    address_line1: line1FromFormatted || current.address_line1,
    city:
      get("locality") ||
      get("administrative_area_level_2") ||
      current.city,
    state: get("administrative_area_level_1") || current.state,
    pincode: get("postal_code") || current.pincode,
    country: get("country") || current.country,
    latitude: place.latitude,
    longitude: place.longitude,
    place_id: place.place_id,
    location_source: source,
  };
}

export function AddressFields({
  value, onChange, errors, disabled, requirePin = false,
}: AddressFieldsProps) {
  const t = useTranslations("Address");
  const [states, setStates] = useState<string[]>([]);
  const [statesError, setStatesError] = useState<string | null>(null);
  const [showMap, setShowMap] = useState<boolean>(requirePin);
  const [mapError, setMapError] = useState<string | null>(null);
  /** Set when an autocomplete pick fires so MapPicker pans to the new
   *  location. Cleared on map drag so the user isn't snapped back. */
  const [mapTarget, setMapTarget] = useState<{ lat: number; lng: number } | null>(null);

  useEffect(() => {
    getIndianStates()
      .then(setStates)
      .catch(() => setStatesError(t("statesLoadError")));
  }, [t]);

  const update = <K extends keyof Address>(key: K, v: Address[K]) =>
    onChange({ ...value, [key]: v });

  const errClass = (k: keyof AddressFieldsErrors) =>
    errors?.[k] ? `${styles.input} ${styles.inputError}` : styles.input;

  return (
    <div className={styles.grid}>
      <div className={`${styles.field} ${styles.span2}`}>
        <AddressAutocomplete
          initialValue={value.address_line1}
          onPlace={(p) => {
            onChange(applyPlace(p, value, "autocomplete"));
            setMapTarget({ lat: p.latitude, lng: p.longitude });
          }}
          disabled={disabled}
        />
      </div>

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

      <div className={`${styles.field} ${styles.span2}`}>
        {!showMap && !requirePin && (
          <button
            type="button"
            className={styles.toggle}
            onClick={() => setShowMap(true)}
          >
            Pin location for accurate delivery
          </button>
        )}
        {showMap && (
          <MapPicker
            initialLat={value.latitude ?? undefined}
            initialLng={value.longitude ?? undefined}
            target={mapTarget}
            requirePin={requirePin}
            onPlace={(p) => onChange(applyPlace(p, value, "pin"))}
            onError={setMapError}
          />
        )}
        {mapError && <span className={styles.error}>{mapError}</span>}
      </div>
    </div>
  );
}
