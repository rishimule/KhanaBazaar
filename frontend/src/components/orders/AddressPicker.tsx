"use client";

import { useEffect, useState } from "react";
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

interface Props {
  value: number | null;
  onChange: (id: number) => void;
  /** When set, each saved address is checked against this store's delivery
   *  radius via /api/v1/geo/serviceability and disabled if outside. */
  storeId?: number;
  /** Optional callback that fires whenever the picked address resolves to
   *  a row with concrete data (id, lat/lng, serviceability). Lets the
   *  parent render a route map / serviceability hint. */
  onSelectedAddress?: (addr: {
    id: number;
    latitude: number | null;
    longitude: number | null;
    serviceable: boolean;
  } | null) => void;
}

export default function AddressPicker({
  value, onChange, storeId, onSelectedAddress,
}: Props) {
  const t = useTranslations("Address");
  const { token } = useAuth();
  const [addresses, setAddresses] = useState<CustomerAddressApi[]>([]);
  const [loading, setLoading] = useState(true);
  /** id → serviceable? Missing entry means "still checking" or "no lat/lng". */
  const [serviceability, setServiceability] = useState<Record<number, boolean>>({});

  useEffect(() => {
    if (!token) return;
    get<CustomerProfileResponse>("/api/v1/customers/me", token)
      .then((data) => {
        setAddresses(data.addresses);
        if (value === null && data.addresses.length > 0) {
          const def = data.addresses.find((a) => a.is_default) ?? data.addresses[0];
          onChange(def.id);
        }
      })
      .finally(() => setLoading(false));
  }, [token, value, onChange]);

  useEffect(() => {
    if (storeId === undefined || addresses.length === 0) return;
    let cancelled = false;
    (async () => {
      const map: Record<number, boolean> = {};
      for (const a of addresses) {
        if (a.address.latitude == null || a.address.longitude == null) {
          map[a.id] = false;
          continue;
        }
        try {
          const r = await checkServiceability(
            a.address.latitude, a.address.longitude, storeId,
          );
          map[a.id] = r.serviceable;
        } catch {
          map[a.id] = false;
        }
      }
      if (!cancelled) setServiceability(map);
    })();
    return () => { cancelled = true; };
  }, [addresses, storeId]);

  // Emit the selected row + its serviceability up to the parent. Must run
  // before any conditional early-return below — Rules of Hooks.
  useEffect(() => {
    if (!onSelectedAddress) return;
    if (value == null) {
      onSelectedAddress(null);
      return;
    }
    const picked = addresses.find((a) => a.id === value);
    if (!picked) {
      onSelectedAddress(null);
      return;
    }
    onSelectedAddress({
      id: picked.id,
      latitude: picked.address.latitude ?? null,
      longitude: picked.address.longitude ?? null,
      serviceable: storeId === undefined ? true : serviceability[picked.id] === true,
    });
  }, [value, addresses, serviceability, storeId, onSelectedAddress]);

  if (loading) return <div className={styles.loading}>{t("pickerLoading")}</div>;
  if (addresses.length === 0) {
    return (
      <div className={styles.empty}>
        {t("pickerEmpty")}{" "}
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
