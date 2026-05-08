"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { Address } from "@/types";
import { getIndianStates } from "@/lib/indian-states";
import { MapPicker } from "@/components/MapPicker";
import { forwardGeocode, type GeoPlace } from "@/lib/geo";
import { ApiError } from "@/lib/api";
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
  /** When true, the parent expects lat/lng to be set before submitting. The
   *  map renders only after a successful "Verify address" geocode. */
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

/** Apply ONLY geo fields from a Place to the address — never the typed text.
 *  The customer enters their address; we use the map to refine where on the
 *  map that address sits. The text fields are authoritative. */
function applyGeoOnly(
  place: GeoPlace,
  current: Address,
  source: "geocoded" | "pin",
): Address {
  return {
    ...current,
    latitude: place.latitude,
    longitude: place.longitude,
    place_id: place.place_id,
    location_source: source,
  };
}

function buildAddressString(a: Address): string {
  return [
    a.address_line1,
    a.address_line2,
    a.landmark,
    a.city,
    a.state,
    a.pincode,
    a.country,
  ]
    .map((p) => (p ?? "").trim())
    .filter(Boolean)
    .join(", ");
}

export function AddressFields({
  value, onChange, errors, disabled, requirePin = false,
}: AddressFieldsProps) {
  const t = useTranslations("Address");
  const [states, setStates] = useState<string[]>([]);
  const [statesError, setStatesError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const showMap = value.latitude != null && value.longitude != null;
  /** Set after a successful verify so the map pans to the new geocode. */
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

  const canVerify =
    value.address_line1.trim().length > 0 &&
    value.city.trim().length > 0 &&
    value.state.length > 0 &&
    /^[1-9]\d{5}$/.test(value.pincode);

  const verifyAddress = async () => {
    setVerifyError(null);
    setMapError(null);
    if (!canVerify) {
      setVerifyError(t("verifyMissingFields"));
      return;
    }
    setVerifying(true);
    try {
      const place = await forwardGeocode(buildAddressString(value));
      onChange(applyGeoOnly(place, value, "geocoded"));
      setMapTarget({ lat: place.latitude, lng: place.longitude });
    } catch (err) {
      const status = (err as ApiError)?.status;
      setVerifyError(
        status === 404 ? t("verifyNotFound") : t("verifyFailed"),
      );
    } finally {
      setVerifying(false);
    }
  };

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

      <div className={`${styles.field} ${styles.span2}`}>
        <button
          type="button"
          className={styles.verifyBtn}
          onClick={verifyAddress}
          disabled={disabled || verifying || !canVerify}
        >
          {verifying
            ? t("verifying")
            : showMap ? t("verifyAgain") : t("verifyAddress")}
        </button>
        <p className={styles.verifyHint}>
          {showMap ? t("verifyAdjustHint") : t("verifyHint")}
          {requirePin && !showMap && (
            <> <span className={styles.required}>{t("verifyRequired")}</span></>
          )}
        </p>
        {verifyError && <span className={styles.error}>{verifyError}</span>}
      </div>

      {showMap && (
        <div className={`${styles.field} ${styles.span2}`}>
          <MapPicker
            initialLat={value.latitude ?? undefined}
            initialLng={value.longitude ?? undefined}
            target={mapTarget}
            requirePin={requirePin}
            onPlace={(p) => onChange(applyGeoOnly(p, value, "pin"))}
            onError={setMapError}
          />
          {mapError && <span className={styles.error}>{mapError}</span>}
        </div>
      )}
    </div>
  );
}
