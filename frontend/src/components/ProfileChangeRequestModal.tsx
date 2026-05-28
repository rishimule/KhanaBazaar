"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState } from "react";
import Modal from "@/components/Modal";
import { GROUP_LABEL } from "@/lib/changeRequests";
import type { SellerProfileChangeGroup } from "@/types";
import styles from "./ProfileChangeRequestModal.module.css";

interface FieldDef {
  name: string;
  label: string;
  type?: "text" | "number" | "tel";
  required?: boolean;
}

const GROUP_FIELDS: Record<SellerProfileChangeGroup, FieldDef[]> = {
  identity: [
    { name: "full_name", label: "Owner full name", required: true },
    { name: "business_name", label: "Business name", required: true },
    { name: "phone", label: "Phone", type: "tel", required: true },
  ],
  address: [
    { name: "street", label: "Street", required: true },
    { name: "city", label: "City", required: true },
    { name: "state", label: "State", required: true },
    { name: "pincode", label: "PIN code", required: true },
    { name: "latitude", label: "Latitude", type: "number", required: true },
    { name: "longitude", label: "Longitude", type: "number", required: true },
  ],
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
    { name: "store_name", label: "Store name", required: true },
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
  submitLabel = "Submit for review",
}: Props) {
  const fields = GROUP_FIELDS[group];
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      fields.map((f) => [f.name, String(currentValues[f.name] ?? "")]),
    ),
  );
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  async function handleSubmit() {
    setError(null);
    setBusy(true);
    const payload: Record<string, unknown> = {};
    for (const f of fields) {
      const v = values[f.name] ?? "";
      if (f.type === "number") {
        payload[f.name] = v === "" ? null : Number(v);
      } else {
        payload[f.name] = v;
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
    return (
      <Modal title="Services edit not supported here" onClose={onClose}>
        <p>
          Services are edited from the Services card on your profile — open it
          from there to submit a change request.
        </p>
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
            {busy ? "…" : submitLabel}
          </button>
        </>
      }
    >
      <p className={styles.subtitle}>Submit change for admin review</p>
      <form
        className={styles.form}
        onSubmit={(e) => {
          e.preventDefault();
          handleSubmit();
        }}
      >
        {fields.map((f) => (
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
          <span>Note for the admin (optional)</span>
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
