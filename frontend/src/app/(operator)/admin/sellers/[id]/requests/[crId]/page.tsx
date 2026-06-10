"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import {
  GROUP_LABEL,
  STATUS_TONE,
  adminApproveCR,
  adminGetSellerCR,
  adminRejectCR,
  adminRequestChangesCR,
} from "@/lib/changeRequests";
import AdminReasonModal from "@/components/admin/AdminReasonModal";
import { AddressFields, emptyAddress } from "@/components/AddressFields";
import ChangeRequestDiffTable from "@/components/ChangeRequestDiffTable";
import ChangeRequestTimeline from "@/components/ChangeRequestTimeline";
import { get } from "@/lib/api";
import type {
  Address,
  LocationSource,
  SellerProfileChangeRequest,
  Service,
} from "@/types";
import styles from "./page.module.css";

type ReasonModal = "request-changes" | "reject" | null;

/**
 * Admin detail view for a single seller profile change request.
 *
 * - Header shows the group name + a status pill. The per-seller layout
 *   already mounts the ImpersonationBanner above this content.
 * - Diff table compares the seller's `baseline_json` against `proposed_json`.
 * - When the CR is in `submitted` state, an "Apply" panel is rendered with
 *   one input per proposed field, prefilled from `proposed_json`. The admin
 *   can either approve as-is, approve with edits (backend detects edits
 *   based on canonical equality), request changes, or reject. The latter
 *   two open a reason modal that gates submission on a 10+ char reason.
 * - When the CR is in a terminal state (approved / rejected / withdrawn) or
 *   has already had changes requested, the apply panel is hidden — only the
 *   diff, banner, and timeline are shown.
 */
export default function AdminCRDetailPage() {
  const params = useParams<{ id: string; crId: string }>();
  const sellerId = Number(params.id);
  const crId = params.crId;
  const { token } = useAuth();
  const tStatus = useTranslations("Shared.changeRequest");
  const [cr, setCr] = useState<SellerProfileChangeRequest | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [applied, setApplied] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [modal, setModal] = useState<ReasonModal>(null);
  const [serviceNames, setServiceNames] = useState<Map<number, string>>(
    new Map(),
  );
  const [addr, setAddr] = useState<Address>(emptyAddress);

  useEffect(() => {
    if (cr?.group !== "services") return;
    let cancelled = false;
    get<Service[]>("/api/v1/catalog/services")
      .then((all) => {
        if (cancelled) return;
        setServiceNames(new Map(all.map((s) => [s.id, s.name])));
      })
      .catch(() => {
        // Names fall back to "Service #<id>".
      });
    return () => {
      cancelled = true;
    };
  }, [cr?.group]);

  const buildAppliedDefaults = useCallback(
    (fresh: SellerProfileChangeRequest): Record<string, string> => {
      const out: Record<string, string> = {};
      for (const [k, v] of Object.entries(fresh.proposed_json)) {
        if (v === null || v === undefined) {
          out[k] = "";
        } else if (typeof v === "object") {
          out[k] = JSON.stringify(v);
        } else {
          out[k] = String(v);
        }
      }
      return out;
    },
    [],
  );

  const refresh = useCallback(async () => {
    if (!token || !crId || !Number.isFinite(sellerId)) return;
    try {
      const fresh = await adminGetSellerCR(token, sellerId, crId);
      setCr(fresh);
      setApplied(buildAppliedDefaults(fresh));
      if (fresh.group === "address") {
        const r = fresh.proposed_json as Record<string, unknown>;
        setAddr({
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
            typeof r["longitude"] === "number"
              ? (r["longitude"] as number)
              : null,
          place_id: (r["place_id"] as string | null) ?? null,
          location_source:
            (r["location_source"] as LocationSource | null) ?? null,
        });
      }
      setNote("");
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Failed to load request");
    }
  }, [token, sellerId, crId, buildAppliedDefaults]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (loadError) {
    return (
      <div className={styles.page}>
        <Link
          href={`/admin/sellers/${sellerId}/requests`}
          className={styles.backLink}
        >
          ← Back to requests
        </Link>
        <div className={styles.errorBanner}>{loadError}</div>
      </div>
    );
  }

  if (!cr) {
    return (
      <div className={styles.page}>
        <p className={styles.muted}>Loading…</p>
      </div>
    );
  }

  const tone = STATUS_TONE[cr.status];
  // The Apply panel + decision buttons are only meaningful while the CR is
  // awaiting review. `changes_requested` is the seller's court — admin must
  // wait for resubmission before approving/rejecting again.
  const canDecide = cr.status === "submitted";

  /** Coerce a form value to the original JSON type of the proposed field. */
  function coerce(key: string, raw: string): unknown {
    const orig = cr?.proposed_json[key];
    if (orig === null || orig === undefined) {
      return raw === "" ? null : raw;
    }
    if (typeof orig === "number") {
      if (raw === "") return null;
      const n = Number(raw);
      return Number.isFinite(n) ? n : raw;
    }
    if (typeof orig === "boolean") {
      const lower = raw.toLowerCase();
      if (lower === "true") return true;
      if (lower === "false") return false;
      return raw;
    }
    if (typeof orig === "object") {
      try {
        return JSON.parse(raw);
      } catch {
        return raw;
      }
    }
    return raw;
  }

  async function handleApprove() {
    if (!token || !cr) return;
    setBusy(true);
    setActionError(null);
    try {
      let payload: Record<string, unknown>;
      if (cr.group === "address") {
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
        for (const [k, v] of Object.entries(applied)) {
          payload[k] = coerce(k, v);
        }
      }
      await adminApproveCR(token, sellerId, cr.id, {
        applied: payload,
        note: note.trim() ? note.trim() : undefined,
      });
      await refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Approve failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.page}>
      <Link
        href={`/admin/sellers/${sellerId}/requests`}
        className={styles.backLink}
      >
        ← Back to requests
      </Link>

      <div className={styles.titleRow}>
        <h1 className={styles.title}>{GROUP_LABEL[cr.group]}</h1>
        <span className={`${styles.pill} ${styles[`tone_${tone}`]}`}>
          {tStatus(`status_${cr.status}`)}
        </span>
      </div>

      <p className={styles.meta}>
        Submitted{" "}
        <time dateTime={cr.created_at}>
          {new Date(cr.created_at).toLocaleString()}
        </time>{" "}
        · {cr.submission_count} submission
        {cr.submission_count === 1 ? "" : "s"}
      </p>

      {cr.status === "changes_requested" && (
        <div className={styles.warnBanner}>
          <strong>Changes requested — awaiting resubmission</strong>
          {cr.admin_note && <p>{cr.admin_note}</p>}
        </div>
      )}
      {cr.status === "approved" && (
        <div className={styles.successBanner}>
          <strong>Approved.</strong>
          {cr.admin_note && <p>{cr.admin_note}</p>}
        </div>
      )}
      {cr.status === "rejected" && (
        <div className={styles.errorBanner}>
          <strong>Rejected.</strong>
          {cr.admin_note && <p>Reason: {cr.admin_note}</p>}
        </div>
      )}
      {cr.status === "withdrawn" && (
        <div className={styles.mutedBanner}>This request was withdrawn.</div>
      )}

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Seller proposed</h2>
        <ChangeRequestDiffTable
          before={cr.baseline_json}
          after={cr.proposed_json}
          beforeLabel="Current"
          afterLabel="Proposed"
          group={cr.group}
          serviceNames={serviceNames}
        />
      </section>

      {cr.status === "approved" && cr.applied_json && (
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Applied</h2>
          <ChangeRequestDiffTable
            before={cr.proposed_json}
            after={cr.applied_json}
            beforeLabel="Seller proposed"
            afterLabel="Applied"
            group={cr.group}
          />
        </section>
      )}

      {canDecide && (
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Apply</h2>
          <p className={styles.helper}>
            Edit any field below before approving — the backend records this as
            &ldquo;approved with edits&rdquo; if the canonical payload differs
            from what the seller proposed.
          </p>
          <div className={styles.applyForm}>
            {cr.group === "address" ? (
              <AddressFields value={addr} onChange={setAddr} requirePin />
            ) : cr.group === "avatar" ? (
              <div className={styles.field}>
                <span className={styles.fieldLabel}>Profile picture</span>
                <div className={styles.avatarCompare}>
                  <figure className={styles.avatarFigure}>
                    <figcaption>Current</figcaption>
                    {String((cr.baseline_json as Record<string, unknown>).avatar_url ?? "") ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={String((cr.baseline_json as Record<string, unknown>).avatar_url)}
                        referrerPolicy="no-referrer"
                        className={styles.avatarPreview}
                        alt="current"
                      />
                    ) : (
                      <span className={styles.avatarNone}>none</span>
                    )}
                  </figure>
                  <figure className={styles.avatarFigure}>
                    <figcaption>Proposed</figcaption>
                    {String((cr.proposed_json as Record<string, unknown>).avatar_url ?? "") ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={String((cr.proposed_json as Record<string, unknown>).avatar_url)}
                        referrerPolicy="no-referrer"
                        className={styles.avatarPreview}
                        alt="proposed"
                      />
                    ) : (
                      <span className={styles.avatarNone}>removal</span>
                    )}
                  </figure>
                </div>
              </div>
            ) : (
              Object.keys(cr.proposed_json)
                .filter((key) => {
                  if (cr.group !== "store_basics") return true;
                  return key === "delivery_radius_km";
                })
                .map((key) => (
                  <label key={key} className={styles.field}>
                    <span className={styles.fieldLabel}>{key}</span>
                    <input
                      className={styles.input}
                      value={applied[key] ?? ""}
                      onChange={(e) =>
                        setApplied((s) => ({ ...s, [key]: e.target.value }))
                      }
                    />
                  </label>
                ))
            )}
            <label className={styles.field}>
              <span className={styles.fieldLabel}>
                Note (optional — visible to seller)
              </span>
              <textarea
                rows={3}
                className={styles.textarea}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                maxLength={500}
              />
            </label>
          </div>

          {actionError && (
            <div className={styles.errorBanner}>{actionError}</div>
          )}

          <div className={styles.actions}>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={handleApprove}
            >
              {busy ? "Working…" : "Approve"}
            </button>
            <button
              type="button"
              className="btn btn-outline"
              disabled={busy}
              onClick={() => {
                setActionError(null);
                setModal("request-changes");
              }}
            >
              Request changes
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy}
              onClick={() => {
                setActionError(null);
                setModal("reject");
              }}
            >
              Reject
            </button>
          </div>
        </section>
      )}

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Timeline</h2>
        <ChangeRequestTimeline events={cr.events} />
      </section>

      {modal === "request-changes" && (
        <AdminReasonModal
          title="Request changes"
          description="Explain what the seller needs to fix. The seller can edit and resubmit."
          confirmLabel="Send back to seller"
          destructive={false}
          onClose={() => setModal(null)}
          onConfirm={async (reason) => {
            if (!token || !cr) return;
            try {
              await adminRequestChangesCR(token, sellerId, cr.id, reason);
              setModal(null);
              await refresh();
            } catch (e) {
              setActionError(
                e instanceof Error ? e.message : "Request changes failed",
              );
            }
          }}
        />
      )}

      {modal === "reject" && (
        <AdminReasonModal
          title="Reject change request"
          description="The seller will see this reason. Rejection is final — they would need to open a new request."
          confirmLabel="Reject"
          destructive
          onClose={() => setModal(null)}
          onConfirm={async (reason) => {
            if (!token || !cr) return;
            try {
              await adminRejectCR(token, sellerId, cr.id, reason);
              setModal(null);
              await refresh();
            } catch (e) {
              setActionError(
                e instanceof Error ? e.message : "Reject failed",
              );
            }
          }}
        />
      )}
    </div>
  );
}
