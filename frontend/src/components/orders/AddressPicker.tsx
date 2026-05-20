"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { checkServiceability } from "@/lib/geo";
import { apiErrorKey } from "@/lib/errors";
import Modal from "@/components/Modal";
import {
  AddressFields,
  emptyAddress,
  type AddressFieldsErrors,
} from "@/components/AddressFields";
import type { Address, CustomerProfile } from "@/types";
import styles from "./AddressPicker.module.css";

interface CustomerAddressApi {
  id: number;
  label: string | null;
  is_default: boolean;
  // Backend AddressPayload uses flat snake_case fields — see
  // backend/app/src/app/schemas/address.py.
  address: {
    address_line1: string;
    address_line2?: string | null;
    city: string;
    state: string;
    pincode: string;
    latitude?: number | null;
    longitude?: number | null;
  };
}

interface CustomerProfileResponse {
  addresses: CustomerAddressApi[];
}

export interface PickerState {
  selectedId: number | null;
  latitude: number | null;
  longitude: number | null;
  /** True when storeId is undefined OR the picked address is in-radius. */
  serviceable: boolean;
  /** True while profile is loading OR any serviceability check unresolved. */
  loading: boolean;
}

interface Props {
  value: number | null;
  onChange: (id: number) => void;
  /** When set, each saved address is checked against this store's delivery
   *  radius via /api/v1/geo/serviceability and disabled if outside. */
  storeId?: number;
  /** Fires whenever the picker's effective state changes. Always called
   *  (never null) so parents can gate on `loading` even before a selection
   *  exists (e.g. zero-serviceable). */
  onStateChange?: (state: PickerState) => void;
}

export default function AddressPicker({
  value, onChange, storeId, onStateChange,
}: Props) {
  const t = useTranslations("Address");
  const tAcc = useTranslations("Account.addresses");
  const tErr = useTranslations("Errors");
  const { token } = useAuth();
  const [addresses, setAddresses] = useState<CustomerAddressApi[]>([]);
  const [profileLoading, setProfileLoading] = useState(true);
  /** id → serviceable? Missing entry means "still checking" or "no lat/lng". */
  const [serviceability, setServiceability] = useState<Record<number, boolean>>({});
  const didAutoSelect = useRef(false);

  const [addModalOpen, setAddModalOpen] = useState(false);
  const [addForm, setAddForm] = useState<{
    label: string;
    is_default: boolean;
    address: Address;
  }>({ label: "", is_default: false, address: emptyAddress() });
  const [addErrors, setAddErrors] = useState<AddressFieldsErrors>({});
  const [modalError, setModalError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [geolocating, setGeolocating] = useState(false);

  useEffect(() => {
    if (!token) return;
    get<CustomerProfileResponse>("/api/v1/customers/me", token)
      .then((data) => { setAddresses(data.addresses); })
      .finally(() => setProfileLoading(false));
  }, [token]);

  useEffect(() => {
    if (storeId === undefined || addresses.length === 0) return;
    let cancelled = false;

    const checks = addresses.map(async (a) => {
      if (a.address.latitude == null || a.address.longitude == null) {
        return [a.id, false] as const;
      }
      try {
        const r = await checkServiceability(
          a.address.latitude, a.address.longitude, storeId,
        );
        return [a.id, r.serviceable] as const;
      } catch {
        return [a.id, false] as const;
      }
    });

    Promise.all(checks).then((entries) => {
      if (cancelled) return;
      setServiceability(Object.fromEntries(entries));
    });

    return () => { cancelled = true; };
  }, [addresses, storeId]);

  const allSettled =
    !profileLoading &&
    (storeId === undefined || addresses.every((a) => a.id in serviceability));

  useEffect(() => {
    if (!allSettled) return;
    if (didAutoSelect.current) return;
    if (value !== null) { didAutoSelect.current = true; return; }
    if (addresses.length === 0) { didAutoSelect.current = true; return; }

    const isOk = (id: number) =>
      storeId === undefined || serviceability[id] === true;

    const def = addresses.find((a) => a.is_default);
    const pick =
      (def && isOk(def.id) ? def : null) ??
      addresses.find((a) => isOk(a.id)) ??
      null;

    if (pick) onChange(pick.id);
    didAutoSelect.current = true;
  }, [allSettled, addresses, serviceability, storeId, value, onChange]);

  useEffect(() => {
    if (!onStateChange) return;
    const picked = value != null ? addresses.find((a) => a.id === value) : undefined;
    onStateChange({
      selectedId: picked?.id ?? null,
      latitude: picked?.address.latitude ?? null,
      longitude: picked?.address.longitude ?? null,
      serviceable:
        picked === undefined
          ? false
          : storeId === undefined
            ? true
            : serviceability[picked.id] === true,
      loading: !allSettled,
    });
  }, [value, addresses, serviceability, storeId, allSettled, onStateChange]);

  const openAddModal = () => {
    setAddForm({ label: "", is_default: false, address: emptyAddress() });
    setAddErrors({});
    setModalError(null);
    setAddModalOpen(true);
  };

  const closeAddModal = () => {
    if (saving) return;
    setAddModalOpen(false);
  };

  const useCurrentLocation = () => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setModalError(tAcc("geolocationUnavailable"));
      return;
    }
    setModalError(null);
    setGeolocating(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude, longitude } = pos.coords;
        try {
          const place = await get<{
            address_line1?: string;
            city?: string;
            state?: string;
            pincode?: string;
            country?: string;
            latitude: number;
            longitude: number;
          }>(`/api/v1/geo/reverse?lat=${latitude}&lng=${longitude}`, token);
          setAddForm((curr) => ({
            ...curr,
            address: {
              ...curr.address,
              address_line1: place.address_line1 ?? curr.address.address_line1,
              city: place.city ?? curr.address.city,
              state: place.state ?? curr.address.state,
              pincode: place.pincode ?? curr.address.pincode,
              country: place.country ?? curr.address.country,
              latitude,
              longitude,
              location_source: "geocoded",
            },
          }));
        } catch {
          setModalError(tAcc("geolocationGeocodeError"));
          setAddForm((curr) => ({
            ...curr,
            address: {
              ...curr.address,
              latitude,
              longitude,
              location_source: "geocoded",
            },
          }));
        } finally {
          setGeolocating(false);
        }
      },
      (err) => {
        setGeolocating(false);
        setModalError(
          err.code === err.PERMISSION_DENIED
            ? tAcc("geolocationDenied")
            : tAcc("geolocationError"),
        );
      },
    );
  };

  const validationErrorsForPrefix = (
    error: unknown,
    prefix: string,
  ): Record<string, string> => {
    const detail = (error as { detail?: unknown })?.detail;
    if (!Array.isArray(detail)) return {};
    return detail.reduce<Record<string, string>>((acc, issue) => {
      const loc = (issue as { loc?: Array<string | number> }).loc;
      const msg = (issue as { msg?: string }).msg;
      if (!Array.isArray(loc) || typeof msg !== "string") return acc;
      const i = loc.indexOf(prefix);
      if (i === -1) return acc;
      const field = loc[i + 1];
      if (typeof field === "string") acc[field] = msg;
      return acc;
    }, {});
  };

  const onSaveAddress = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token || saving) return;
    setSaving(true);
    setAddErrors({});
    setModalError(null);
    const prevIds = new Set(addresses.map((a) => a.id));
    const payload = {
      label: addForm.label.trim().length > 0 ? addForm.label.trim() : null,
      is_default: addForm.is_default,
      address: addForm.address,
    };
    try {
      const next = await post<CustomerProfile>(
        "/api/v1/customers/me/addresses",
        payload,
        token,
      );
      const newId = next.addresses.find((a) => !prevIds.has(a.id))?.id ?? null;
      setAddresses(
        next.addresses.map((a) => ({
          id: a.id,
          label: a.label,
          is_default: a.is_default,
          address: {
            address_line1: a.address.address_line1,
            address_line2: a.address.address_line2 ?? null,
            city: a.address.city,
            state: a.address.state,
            pincode: a.address.pincode,
            latitude: a.address.latitude ?? null,
            longitude: a.address.longitude ?? null,
          },
        })),
      );
      setAddModalOpen(false);
      if (newId != null) {
        onChange(newId);
      }
    } catch (error) {
      setAddErrors(
        validationErrorsForPrefix(error, "address") as AddressFieldsErrors,
      );
      const key = apiErrorKey(error);
      if (key) {
        setModalError(tErr(key.replace(/^Errors\./, "")));
      } else {
        setModalError(tAcc("saveAddressError"));
      }
    } finally {
      setSaving(false);
    }
  };

  const renderAddModal = () => (
    <Modal title={tAcc("addAddressFormTitle")} onClose={closeAddModal} size="wide">
      <form className={styles.modalBody} onSubmit={onSaveAddress}>
        {modalError && <div className={styles.modalError}>{modalError}</div>}

        <div className={styles.modalField}>
          <label className={styles.label} htmlFor="add-address-label">
            {tAcc("labelLabel")}
          </label>
          <input
            id="add-address-label"
            className={styles.modalInput}
            value={addForm.label}
            onChange={(e) =>
              setAddForm((curr) => ({ ...curr, label: e.target.value }))
            }
            placeholder={tAcc("labelPlaceholder")}
            maxLength={60}
            disabled={saving}
          />
        </div>

        <button
          type="button"
          className={styles.addBtn}
          onClick={useCurrentLocation}
          disabled={saving || geolocating}
        >
          {geolocating ? tAcc("geolocating") : tAcc("useCurrentLocation")}
        </button>

        <AddressFields
          value={addForm.address}
          onChange={(address) =>
            setAddForm((curr) => ({ ...curr, address }))
          }
          errors={addErrors}
          disabled={saving}
        />

        <label className={styles.modalCheckboxRow}>
          <input
            type="checkbox"
            checked={addForm.is_default}
            onChange={(e) =>
              setAddForm((curr) => ({ ...curr, is_default: e.target.checked }))
            }
            disabled={saving}
          />
          {tAcc("makeDefault")}
        </label>

        <div className={styles.modalActions}>
          <button
            type="button"
            className="btn btn-outline"
            onClick={closeAddModal}
            disabled={saving}
          >
            {tAcc("cancel")}
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={saving}
          >
            {saving ? tAcc("saving") : tAcc("saveAddress")}
          </button>
        </div>
      </form>
    </Modal>
  );

  if (profileLoading) return <div className={styles.loading}>{t("pickerLoading")}</div>;
  if (addresses.length === 0) {
    return (
      <>
        <div className={styles.empty}>
          {t("pickerEmpty")}
          <div className={styles.emptyActions}>
            <button
              type="button"
              className={styles.addBtn}
              onClick={openAddModal}
            >
              + {tAcc("addAddress")}
            </button>
          </div>
        </div>
        {addModalOpen && renderAddModal()}
      </>
    );
  }

  const hasAnyServiceable =
    storeId === undefined ||
    addresses.some((a) => serviceability[a.id] === true);

  if (allSettled && !hasAnyServiceable) {
    return (
      <>
        <div className={styles.empty}>
          {t("noServiceableTitle")}
          <div className={styles.emptyActions}>
            <button
              type="button"
              className={styles.addBtn}
              onClick={openAddModal}
            >
              + {tAcc("addAddress")}
            </button>
          </div>
        </div>
        {addModalOpen && renderAddModal()}
      </>
    );
  }

  const isDisabled = (id: number) =>
    storeId !== undefined && serviceability[id] === false;

  return (
    <>
      <div className={styles.picker}>
        <div className={styles.header}>
          <label htmlFor="address-picker" className={styles.label}>{t("deliverTo")}</label>
          <button
            type="button"
            className={styles.addBtn}
            onClick={openAddModal}
          >
            + {tAcc("addAddress")}
          </button>
        </div>
        <select
          id="address-picker"
          value={value ?? ""}
          onChange={(e) => onChange(Number(e.target.value))}
          className={styles.select}
        >
          {addresses.map((a) => (
            <option key={a.id} value={a.id} disabled={isDisabled(a.id)}>
              {(a.label ?? t("fallbackLabel"))} — {a.address.address_line1}, {a.address.city} {a.address.pincode}
              {isDisabled(a.id) ? " (Outside delivery area)" : ""}
            </option>
          ))}
        </select>
      </div>
      {addModalOpen && renderAddModal()}
    </>
  );
}
