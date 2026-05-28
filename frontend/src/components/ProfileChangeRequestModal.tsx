"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import Modal from "@/components/Modal";
import { get } from "@/lib/api";
import { AddressFields, emptyAddress } from "@/components/AddressFields";
import { GROUP_LABEL } from "@/lib/changeRequests";
import type {
  Address,
  LocationSource,
  SellerProfileChangeGroup,
  Service,
} from "@/types";
import styles from "./ProfileChangeRequestModal.module.css";

interface FieldDef {
  name: string;
  label: string;
  type?: "text" | "number" | "tel";
  required?: boolean;
}

interface ServiceRow {
  service_id: number;
  name: string;
  selected: boolean;
  min_order_value: string;
}

const GROUP_FIELDS: Record<SellerProfileChangeGroup, FieldDef[]> = {
  identity: [
    { name: "full_name", label: "Owner full name", required: true },
    { name: "business_name", label: "Business name", required: true },
    { name: "phone", label: "Phone", type: "tel", required: true },
  ],
  // The address group uses the full <AddressFields> component (map picker +
  // autocomplete + manual entry); see render path below — no field list here.
  address: [],
  legal: [
    { name: "gst_number", label: "GST number" },
    { name: "fssai_license", label: "FSSAI license" },
  ],
  banking: [
    { name: "bank_account_number", label: "Bank account number" },
    { name: "bank_ifsc", label: "IFSC code" },
  ],
  // Services group uses a different sub-form (see profile services card), not
  // handled by this generic modal.
  services: [],
  store_basics: [
    {
      name: "delivery_radius_km",
      label: "Delivery radius (km)",
      type: "number",
      required: true,
    },
  ],
};

interface Props {
  group: SellerProfileChangeGroup;
  currentValues: Record<string, unknown>;
  open: boolean;
  onClose: () => void;
  onSubmit: (proposed: Record<string, unknown>, note?: string) => Promise<void>;
  submitLabel?: string;
}

/**
 * Generic per-group profile-edit modal that submits a change request for
 * admin review. Each group renders a small input set (identity, address,
 * legal, banking, store_basics); the `services` group is intentionally
 * routed elsewhere and shows a redirect message here.
 */
export default function ProfileChangeRequestModal({
  group,
  currentValues,
  open,
  onClose,
  onSubmit,
  submitLabel,
}: Props) {
  const tCR = useTranslations("Seller.changeRequests");
  const resolvedSubmitLabel = submitLabel ?? tCR("submitForReview");
  const fields = GROUP_FIELDS[group];
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      fields.map((f) => [f.name, String(currentValues[f.name] ?? "")]),
    ),
  );
  const initialAddress: Address = (() => {
    if (group !== "address") return emptyAddress();
    const r = currentValues as Record<string, unknown>;
    return {
      address_line1: String(r["address_line1"] ?? ""),
      address_line2: (r["address_line2"] as string | null) ?? null,
      landmark: (r["landmark"] as string | null) ?? null,
      city: String(r["city"] ?? ""),
      state: String(r["state"] ?? ""),
      pincode: String(r["pincode"] ?? ""),
      country: String(r["country"] ?? "India"),
      latitude:
        typeof r["latitude"] === "number" ? (r["latitude"] as number) : null,
      longitude:
        typeof r["longitude"] === "number" ? (r["longitude"] as number) : null,
      place_id: (r["place_id"] as string | null) ?? null,
      location_source:
        (r["location_source"] as LocationSource | null) ?? null,
    };
  })();
  const [addr, setAddr] = useState<Address>(initialAddress);
  const [services, setServices] = useState<ServiceRow[]>([]);
  const [servicesLoading, setServicesLoading] = useState(group === "services");
  useEffect(() => {
    if (group !== "services" || !open) return;
    let cancelled = false;
    setServicesLoading(true);
    const subscribed = new Map<number, string>();
    const subRaw = currentValues["services"];
    if (Array.isArray(subRaw)) {
      for (const row of subRaw) {
        const r = row as Record<string, unknown>;
        subscribed.set(
          Number(r["service_id"]),
          String(r["min_order_value"] ?? "0"),
        );
      }
    }
    get<Service[]>("/api/v1/catalog/services")
      .then((all) => {
        if (cancelled) return;
        setServices(
          all
            .filter((s) => s.is_active)
            .map((s) => ({
              service_id: s.id,
              name: s.name,
              selected: subscribed.has(s.id),
              min_order_value: subscribed.get(s.id) ?? "0",
            })),
        );
      })
      .catch(() => {
        if (cancelled) return;
        setServices([]);
      })
      .finally(() => {
        if (!cancelled) setServicesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [group, open, currentValues]);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  async function handleSubmit() {
    setError(null);
    setBusy(true);
    let payload: Record<string, unknown>;
    if (group === "services") {
      payload = {
        services: services
          .filter((s) => s.selected)
          .map((s) => ({
            service_id: s.service_id,
            min_order_value:
              s.min_order_value === "" ? 0 : Number(s.min_order_value),
          })),
      };
    } else if (group === "address") {
      payload = {
        address_line1: addr.address_line1.trim(),
        address_line2: addr.address_line2 || null,
        landmark: addr.landmark || null,
        city: addr.city.trim(),
        state: addr.state,
        pincode: addr.pincode.trim(),
        country: addr.country || "India",
        latitude: addr.latitude,
        longitude: addr.longitude,
        place_id: addr.place_id ?? null,
        location_source: addr.location_source ?? null,
      };
    } else {
      payload = {};
      for (const f of fields) {
        const v = values[f.name] ?? "";
        if (f.type === "number") {
          payload[f.name] = v === "" ? null : Number(v);
        } else {
          payload[f.name] = v;
        }
      }
    }
    try {
      await onSubmit(payload, note || undefined);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Submission failed");
    } finally {
      setBusy(false);
    }
  }

  if (group === "services") {
    const selectedCount = services.filter((s) => s.selected).length;
    return (
      <Modal
        title={`Edit ${GROUP_LABEL[group]}`}
        onClose={onClose}
        footer={
          <>
            <button
              type="button"
              className="btn btn-outline"
              onClick={onClose}
              disabled={busy}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || selectedCount === 0}
              onClick={handleSubmit}
            >
              {busy ? "…" : resolvedSubmitLabel}
            </button>
          </>
        }
      >
        <p className={styles.subtitle}>{tCR("modalSubtitle")}</p>
        <form
          className={styles.form}
          onSubmit={(e) => {
            e.preventDefault();
            handleSubmit();
          }}
        >
          {servicesLoading && <p>Loading services…</p>}
          {!servicesLoading && services.length === 0 && (
            <p className={styles.error}>
              Could not load services. Try again later.
            </p>
          )}
          {!servicesLoading &&
            services.map((row, idx) => (
              <div key={row.service_id} className={styles.field}>
                <label className={styles.checkboxRow}>
                  <input
                    type="checkbox"
                    checked={row.selected}
                    onChange={(e) =>
                      setServices((rows) =>
                        rows.map((r, i) =>
                          i === idx ? { ...r, selected: e.target.checked } : r,
                        ),
                      )
                    }
                  />
                  <span>{row.name}</span>
                </label>
                {row.selected && (
                  <label className={styles.subField}>
                    <span>Minimum order value (₹)</span>
                    <input
                      type="number"
                      min={0}
                      max={100000}
                      step={10}
                      value={row.min_order_value}
                      onChange={(e) =>
                        setServices((rows) =>
                          rows.map((r, i) =>
                            i === idx
                              ? { ...r, min_order_value: e.target.value }
                              : r,
                          ),
                        )
                      }
                    />
                  </label>
                )}
              </div>
            ))}
          {!servicesLoading && services.length > 0 && selectedCount === 0 && (
            <p className={styles.error}>Select at least one service.</p>
          )}
          <label className={styles.field}>
            <span>{tCR("noteHelp")}</span>
            <textarea
              maxLength={300}
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          {error && <p className={styles.error}>{error}</p>}
        </form>
      </Modal>
    );
  }

  return (
    <Modal
      title={`Edit ${GROUP_LABEL[group]}`}
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            className="btn btn-outline"
            onClick={onClose}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={handleSubmit}
          >
            {busy ? "…" : resolvedSubmitLabel}
          </button>
        </>
      }
    >
      <p className={styles.subtitle}>{tCR("modalSubtitle")}</p>
      <form
        className={styles.form}
        onSubmit={(e) => {
          e.preventDefault();
          handleSubmit();
        }}
      >
        {group === "address" && (
          <AddressFields value={addr} onChange={setAddr} requirePin />
        )}
        {group !== "address" &&
          fields.map((f) => (
            <label key={f.name} className={styles.field}>
              <span>{f.label}</span>
              <input
                type={f.type ?? "text"}
                value={values[f.name] ?? ""}
                required={f.required}
                onChange={(e) =>
                  setValues((vs) => ({ ...vs, [f.name]: e.target.value }))
                }
              />
            </label>
          ))}
        <label className={styles.field}>
          <span>{tCR("noteHelp")}</span>
          <textarea
            maxLength={300}
            rows={3}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        {error && <p className={styles.error}>{error}</p>}
      </form>
    </Modal>
  );
}
