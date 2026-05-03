"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
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
  };
}

interface CustomerProfileResponse {
  addresses: CustomerAddressApi[];
}

interface Props {
  value: number | null;
  onChange: (id: number) => void;
}

export default function AddressPicker({ value, onChange }: Props) {
  const { token } = useAuth();
  const [addresses, setAddresses] = useState<CustomerAddressApi[]>([]);
  const [loading, setLoading] = useState(true);

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

  if (loading) return <div className={styles.loading}>Loading addresses…</div>;
  if (addresses.length === 0) {
    return (
      <div className={styles.empty}>
        No saved address.{" "}
        <Link href="/account/settings" className={styles.link}>Add one</Link>
      </div>
    );
  }

  return (
    <div className={styles.picker}>
      <label htmlFor="address-picker" className={styles.label}>Deliver to</label>
      <select
        id="address-picker"
        value={value ?? ""}
        onChange={(e) => onChange(Number(e.target.value))}
        className={styles.select}
      >
        {addresses.map((a) => (
          <option key={a.id} value={a.id}>
            {(a.label ?? "Address")} — {a.address.address_line1}, {a.address.city} {a.address.pincode}
          </option>
        ))}
      </select>
    </div>
  );
}
