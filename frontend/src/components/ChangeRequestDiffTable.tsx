"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState, type ReactNode } from "react";
import type { SellerProfileChangeGroup } from "@/types";
import styles from "./ChangeRequestDiffTable.module.css";

interface Props {
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  beforeLabel?: string;
  afterLabel?: string;
  /** When set, field keys + values are rendered with group-aware friendly
   *  formatters (labels in English, account-number masking, services rendered
   *  as named chips, etc.). Leave undefined for raw JSON-style rendering. */
  group?: SellerProfileChangeGroup;
  /** Map of service_id -> human name. Required when group=services. */
  serviceNames?: Map<number, string>;
}

/** Per-group canonical key set. When `group` is provided, rows for keys
 *  outside this set are hidden (drops stale fields like `store_name` from
 *  pre-cleanup `store_basics` rows). */
const ALLOWED_KEYS: Partial<Record<SellerProfileChangeGroup, Set<string>>> = {
  identity: new Set(["full_name", "business_name", "phone"]),
  address: new Set([
    "address_line1",
    "address_line2",
    "landmark",
    "city",
    "state",
    "pincode",
    "country",
    "latitude",
    "longitude",
  ]),
  legal: new Set(["gst_number", "fssai_license"]),
  banking: new Set(["bank_account_number", "bank_ifsc"]),
  services: new Set(["services"]),
  store_basics: new Set(["delivery_radius_km"]),
};

const FIELD_LABELS: Record<string, string> = {
  // identity
  full_name: "Owner name",
  business_name: "Business name",
  phone: "Phone",
  // address
  address_line1: "Address line 1",
  address_line2: "Address line 2",
  landmark: "Landmark",
  city: "City",
  state: "State",
  pincode: "PIN code",
  country: "Country",
  latitude: "Latitude",
  longitude: "Longitude",
  // legal
  gst_number: "GST number",
  fssai_license: "FSSAI license",
  // banking
  bank_account_number: "Account number",
  bank_ifsc: "IFSC code",
  // services
  services: "Services",
  // store_basics
  store_name: "Store name",
  delivery_radius_km: "Delivery radius",
};

function maskAccount(n: string): string {
  if (n.length < 4) return n;
  const last4 = n.slice(-4);
  return `•••• •••• ${last4}`;
}

interface ServiceEntry {
  service_id: number;
  min_order_value: number;
  delivery_eta_min_minutes?: number;
  delivery_eta_max_minutes?: number;
}

function isServiceList(v: unknown): v is ServiceEntry[] {
  return (
    Array.isArray(v) &&
    v.every(
      (e) =>
        e !== null &&
        typeof e === "object" &&
        "service_id" in (e as Record<string, unknown>),
    )
  );
}

function renderServiceChips(
  rows: ServiceEntry[],
  serviceNames: Map<number, string> | undefined,
): ReactNode {
  if (rows.length === 0) return <span className={styles.muted}>None</span>;
  return (
    <ul className={styles.chipList}>
      {rows.map((r) => {
        const name = serviceNames?.get(r.service_id) ?? `Service #${r.service_id}`;
        return (
          <li key={r.service_id} className={styles.chip}>
            <span className={styles.chipName}>{name}</span>
            <span className={styles.chipMeta}>
              min ₹{Math.round(r.min_order_value)}
              {r.delivery_eta_min_minutes != null &&
                r.delivery_eta_max_minutes != null &&
                ` · ETA ${r.delivery_eta_min_minutes}–${r.delivery_eta_max_minutes} min`}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function formatValue(
  group: SellerProfileChangeGroup | undefined,
  key: string,
  value: unknown,
  serviceNames: Map<number, string> | undefined,
): ReactNode {
  if (value === null || value === undefined || value === "") {
    return <span className={styles.muted}>—</span>;
  }
  if (group === "services" && key === "services" && isServiceList(value)) {
    return renderServiceChips(value, serviceNames);
  }
  if (group === "banking" && key === "bank_account_number" && typeof value === "string") {
    return <span className={styles.mono}>{maskAccount(value)}</span>;
  }
  if (group === "banking" && key === "bank_ifsc" && typeof value === "string") {
    return <span className={styles.mono}>{value}</span>;
  }
  if (key === "delivery_radius_km" && typeof value === "number") {
    return <>{value} km</>;
  }
  if (typeof value === "object") {
    return <span className={styles.muted}>{JSON.stringify(value)}</span>;
  }
  return String(value);
}

function fieldLabel(key: string): string {
  return FIELD_LABELS[key] ?? key.replace(/_/g, " ");
}

/**
 * Side-by-side diff of two records. When `group` is provided, field keys and
 * values get friendly per-group rendering (human labels, masked accounts,
 * service chips). Otherwise falls back to raw JSON-style rendering used by
 * admin views that need precision.
 */
export default function ChangeRequestDiffTable({
  before,
  after,
  beforeLabel = "Current",
  afterLabel = "Proposed",
  group,
  serviceNames,
}: Props) {
  const [showUnchanged, setShowUnchanged] = useState(false);
  const allowed = group !== undefined ? ALLOWED_KEYS[group] : undefined;
  const keys = Array.from(
    new Set([...Object.keys(before), ...Object.keys(after)]),
  ).filter((k) => (allowed ? allowed.has(k) : true));
  const rows = keys.map((k) => ({
    key: k,
    before: before[k],
    after: after[k],
    changed: JSON.stringify(before[k]) !== JSON.stringify(after[k]),
  }));
  const visible = showUnchanged ? rows : rows.filter((r) => r.changed);
  const hasUnchanged = rows.some((r) => !r.changed);

  const renderCell = (key: string, value: unknown): ReactNode => {
    if (group !== undefined) {
      return formatValue(group, key, value, serviceNames);
    }
    if (value === null || value === undefined || value === "") return "—";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  };

  return (
    <div className={styles.wrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Field</th>
            <th>{beforeLabel}</th>
            <th>{afterLabel}</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((r) => (
            <tr key={r.key} className={r.changed ? styles.changed : undefined}>
              <td className={styles.fieldName}>
                {group !== undefined ? fieldLabel(r.key) : r.key}
              </td>
              <td>{renderCell(r.key, r.before)}</td>
              <td>{renderCell(r.key, r.after)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {hasUnchanged && (
        <button
          type="button"
          className={styles.toggle}
          onClick={() => setShowUnchanged((v) => !v)}
        >
          {showUnchanged ? "Hide unchanged" : "Show unchanged"}
        </button>
      )}
    </div>
  );
}
