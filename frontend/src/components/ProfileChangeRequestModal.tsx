"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import Modal from "@/components/Modal";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import {
  normalizeIndianPhone,
  phoneOtpErrorMessage,
  requestSellerPhoneOtp,
  verifySellerPhoneOtp,
} from "@/lib/sellerPhone";
import { AddressFields, emptyAddress } from "@/components/AddressFields";
import { GROUP_LABEL } from "@/lib/changeRequests";
import {
  normalizeField,
  profileEditErrorMessage,
  validateField,
} from "@/lib/sellerProfileValidation";
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
  delivery_eta_min_minutes: string;
  delivery_eta_max_minutes: string;
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
  onSubmit: (
    proposed: Record<string, unknown>,
    note?: string,
    phoneChangeToken?: string,
  ) => Promise<void>;
  submitLabel?: string;
  /**
   * The seller's ACTUAL current phone, used as the verification baseline for
   * identity edits. Defaults to `currentValues.phone`. The resubmit flow seeds
   * `currentValues` from the CR's proposed payload (not the live profile), so
   * it must pass the real current phone here (`cr.baseline_json.phone`) — else
   * a phone change can skip the verify step and dead-end at a 422.
   */
  currentPhone?: string;
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
  currentPhone,
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
    const subscribed = new Map<
      number,
      { min: string; etaMin: string; etaMax: string }
    >();
    const subRaw = currentValues["services"];
    if (Array.isArray(subRaw)) {
      for (const row of subRaw) {
        const r = row as Record<string, unknown>;
        subscribed.set(Number(r["service_id"]), {
          min: String(r["min_order_value"] ?? "0"),
          etaMin: String(r["delivery_eta_min_minutes"] ?? "30"),
          etaMax: String(r["delivery_eta_max_minutes"] ?? "60"),
        });
      }
    }
    get<Service[]>("/api/v1/catalog/services")
      .then((all) => {
        if (cancelled) return;
        setServices(
          all
            .filter((s) => s.is_active)
            .map((s) => {
              const sub = subscribed.get(s.id);
              return {
                service_id: s.id,
                name: s.name,
                selected: subscribed.has(s.id),
                min_order_value: sub?.min ?? "0",
                delivery_eta_min_minutes: sub?.etaMin ?? "30",
                delivery_eta_max_minutes: sub?.etaMax ?? "60",
              };
            }),
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
  // Seed from the initial values so a pre-filled/autofilled invalid value
  // surfaces its message immediately, rather than leaving Submit disabled with
  // no visible reason. Valid/empty-optional fields seed to null (no message).
  const [errors, setErrors] = useState<Record<string, string | null>>(() =>
    Object.fromEntries(
      fields.map((f) => [
        f.name,
        validateField(f.name, String(currentValues[f.name] ?? "")),
      ]),
    ),
  );

  // The active group validates when every one of its generic fields passes.
  // Phone (identity) is gated separately by phoneVerified; address/services use
  // their own flows and have empty `fields`, so this is true for them.
  const groupValid = fields.every(
    (f) => validateField(f.name, values[f.name] ?? "") === null,
  );

  // --- Identity phone-change verification (OTP on the NEW number) ---
  // Compare against the canonical form so cosmetic formatting (spaces/hyphens,
  // missing +91) doesn't flip "changed"/"verified" out from under the backend,
  // which binds the token to normalize_phone()'s canonical value.
  const { token: authToken } = useAuth();
  const baselinePhone = normalizeIndianPhone(
    String(currentPhone ?? currentValues["phone"] ?? "").trim(),
  );
  const phoneInput = (values["phone"] ?? "").trim();
  const phoneInputNorm = normalizeIndianPhone(phoneInput);
  const phoneChanged =
    group === "identity" && phoneInputNorm !== baselinePhone;
  const [otpSent, setOtpSent] = useState(false);
  const [otpCode, setOtpCode] = useState("");
  const [phoneChangeToken, setPhoneChangeToken] = useState<string | undefined>();
  const [verifiedPhone, setVerifiedPhone] = useState<string | undefined>();
  const [otpBusy, setOtpBusy] = useState(false);

  // Editing the phone after verifying invalidates the token.
  useEffect(() => {
    if (verifiedPhone !== undefined && phoneInputNorm !== verifiedPhone) {
      setPhoneChangeToken(undefined);
      setVerifiedPhone(undefined);
      setOtpSent(false);
      setOtpCode("");
    }
  }, [phoneInputNorm, verifiedPhone]);

  const phoneVerified =
    !phoneChanged ||
    (!!phoneChangeToken && verifiedPhone === phoneInputNorm);

  async function handleSendOtp() {
    if (!authToken) return;
    setError(null);
    setOtpBusy(true);
    try {
      await requestSellerPhoneOtp(authToken, phoneInputNorm);
      setOtpSent(true);
    } catch (e) {
      setError(phoneOtpErrorMessage(e));
    } finally {
      setOtpBusy(false);
    }
  }

  async function handleVerifyOtp() {
    if (!authToken) return;
    setError(null);
    setOtpBusy(true);
    try {
      const tok = await verifySellerPhoneOtp(
        authToken,
        phoneInputNorm,
        otpCode.trim(),
      );
      setPhoneChangeToken(tok);
      setVerifiedPhone(phoneInputNorm);
    } catch (e) {
      setError(phoneOtpErrorMessage(e));
    } finally {
      setOtpBusy(false);
    }
  }

  if (!open) return null;

  async function handleSubmit() {
    setError(null);
    if (group === "services") {
      const badEta = services
        .filter((s) => s.selected)
        .some(
          (s) =>
            Number(s.delivery_eta_min_minutes || 30) >
            Number(s.delivery_eta_max_minutes || 60),
        );
      if (badEta) {
        setError("Maximum delivery time must be at least the minimum.");
        return;
      }
    }
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
            delivery_eta_min_minutes:
              s.delivery_eta_min_minutes === "" ? 30 : Number(s.delivery_eta_min_minutes),
            delivery_eta_max_minutes:
              s.delivery_eta_max_minutes === "" ? 60 : Number(s.delivery_eta_max_minutes),
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
          payload[f.name] = v.trim();
        }
      }
    }
    try {
      await onSubmit(payload, note || undefined, phoneChangeToken);
      onClose();
    } catch (e) {
      setError(profileEditErrorMessage(e));
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
                  <>
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
                    <label className={styles.subField}>
                      <span>Delivery time — min (minutes)</span>
                      <input
                        type="number"
                        min={1}
                        max={20160}
                        step={5}
                        value={row.delivery_eta_min_minutes}
                        onChange={(e) =>
                          setServices((rows) =>
                            rows.map((r, i) =>
                              i === idx
                                ? { ...r, delivery_eta_min_minutes: e.target.value }
                                : r,
                            ),
                          )
                        }
                      />
                    </label>
                    <label className={styles.subField}>
                      <span>Delivery time — max (minutes)</span>
                      <input
                        type="number"
                        min={1}
                        max={20160}
                        step={5}
                        value={row.delivery_eta_max_minutes}
                        onChange={(e) =>
                          setServices((rows) =>
                            rows.map((r, i) =>
                              i === idx
                                ? { ...r, delivery_eta_max_minutes: e.target.value }
                                : r,
                            ),
                          )
                        }
                      />
                    </label>
                  </>
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
          {error && <p role="alert" className={styles.error}>{error}</p>}
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
            disabled={busy || !phoneVerified || !groupValid}
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
          fields.map((f) => {
            // Identity phone: lock the +91 country code, accept 10 digits only.
            // `values.phone` stays the full canonical "+91XXXXXXXXXX" so the
            // verify/normalize/payload logic downstream is unchanged.
            if (group === "identity" && f.name === "phone") {
              const local = (values["phone"] ?? "").replace(/^\+91/, "");
              return (
                <label key={f.name} className={styles.field}>
                  <span>{f.label}</span>
                  <div className={styles.phoneRow}>
                    <span className={styles.phonePrefix}>+91</span>
                    <input
                      type="tel"
                      inputMode="numeric"
                      value={local}
                      required={f.required}
                      maxLength={10}
                      placeholder="10-digit number"
                      onChange={(e) => {
                        const digits = e.target.value
                          .replace(/\D/g, "")
                          .slice(0, 10);
                        setValues((vs) => ({ ...vs, phone: `+91${digits}` }));
                      }}
                    />
                  </div>
                </label>
              );
            }
            return (
              <label key={f.name} className={styles.field}>
                <span>{f.label}</span>
                <input
                  type={f.type ?? "text"}
                  value={values[f.name] ?? ""}
                  required={f.required}
                  aria-invalid={errors[f.name] ? true : undefined}
                  aria-describedby={errors[f.name] ? `${f.name}-error` : undefined}
                  onChange={(e) => {
                    const v = normalizeField(f.name, e.target.value);
                    setValues((vs) => ({ ...vs, [f.name]: v }));
                    setErrors((es) => ({ ...es, [f.name]: validateField(f.name, v) }));
                  }}
                  onBlur={(e) => {
                    const v = normalizeField(f.name, e.target.value);
                    setValues((vs) => ({ ...vs, [f.name]: v }));
                    setErrors((es) => ({ ...es, [f.name]: validateField(f.name, v) }));
                  }}
                />
                {errors[f.name] && (
                  <span
                    id={`${f.name}-error`}
                    role="alert"
                    className={styles.fieldError}
                  >
                    {errors[f.name]}
                  </span>
                )}
              </label>
            );
          })}
        {phoneChanged && !phoneVerified && (
          <div className={styles.field}>
            <span>Verify new phone number</span>
            {!otpSent ? (
              <button
                type="button"
                className="btn btn-outline"
                disabled={otpBusy || phoneInput.length === 0}
                onClick={handleSendOtp}
              >
                {otpBusy ? "Sending…" : "Send code"}
              </button>
            ) : (
              <>
                <input
                  type="text"
                  inputMode="numeric"
                  placeholder="Enter code"
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value)}
                />
                <div className={styles.otpActions}>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={otpBusy || otpCode.trim().length === 0}
                    onClick={handleVerifyOtp}
                  >
                    {otpBusy ? "Verifying…" : "Verify"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    disabled={otpBusy}
                    onClick={handleSendOtp}
                  >
                    Resend
                  </button>
                </div>
              </>
            )}
          </div>
        )}
        {phoneChanged && phoneVerified && (
          <p className={styles.subtitle}>✓ New phone verified.</p>
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
        {error && <p role="alert" className={styles.error}>{error}</p>}
      </form>
    </Modal>
  );
}
