"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { checkServiceability } from "@/lib/geo";
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
  const { token } = useAuth();
  const [addresses, setAddresses] = useState<CustomerAddressApi[]>([]);
  const [profileLoading, setProfileLoading] = useState(true);
  /** id → serviceable? Missing entry means "still checking" or "no lat/lng". */
  const [serviceability, setServiceability] = useState<Record<number, boolean>>({});
  const didAutoSelect = useRef(false);

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

  if (profileLoading) return <div className={styles.loading}>{t("pickerLoading")}</div>;
  if (addresses.length === 0) {
    return (
      <div className={styles.empty}>
        {t("pickerEmpty")}{" "}
        <Link href="/account/settings" className={styles.link}>{t("pickerAddOne")}</Link>
      </div>
    );
  }

  const hasAnyServiceable =
    storeId === undefined ||
    addresses.some((a) => serviceability[a.id] === true);

  if (allSettled && !hasAnyServiceable) {
    return (
      <div className={styles.empty}>
        {t("noServiceableTitle")}{" "}
        <Link href="/account/settings" className={styles.link}>{t("pickerAddOne")}</Link>
      </div>
    );
  }

  const isDisabled = (id: number) =>
    storeId !== undefined && serviceability[id] === false;

  return (
    <div className={styles.picker}>
      <label htmlFor="address-picker" className={styles.label}>{t("deliverTo")}</label>
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
  );
}
