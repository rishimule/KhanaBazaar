"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import {
  GROUP_LABEL,
  STATUS_TONE,
  getMyChangeRequest,
  isOpen,
  resubmitMyChangeRequest,
  withdrawMyChangeRequest,
} from "@/lib/changeRequests";
import ChangeRequestDiffTable from "@/components/ChangeRequestDiffTable";
import ChangeRequestTimeline from "@/components/ChangeRequestTimeline";
import ProfileChangeRequestModal from "@/components/ProfileChangeRequestModal";
import type { SellerProfileChangeRequest } from "@/types";
import styles from "./page.module.css";

/**
 * Seller-facing detail page for a single profile change request.
 *
 * Renders the diff (current → proposed and, when approved, proposed →
 * applied), the event timeline, and per-status affordances:
 *
 *  - submitted          → withdraw available
 *  - changes_requested  → withdraw OR edit & resubmit (modal)
 *  - approved           → read-only with the applied diff
 *  - rejected           → read-only with the admin reason banner
 *  - withdrawn          → read-only
 */
export default function SellerRequestDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();
  const { token } = useAuth();
  const [cr, setCr] = useState<SellerProfileChangeRequest | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);

  const refresh = useCallback(async () => {
    if (!token || !id) return;
    try {
      const fresh = await getMyChangeRequest(token, id);
      setCr(fresh);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Failed to load request");
    }
  }, [token, id]);

  useEffect(() => {
    if (!token || !id) return;
    let cancelled = false;
    getMyChangeRequest(token, id)
      .then((fresh) => {
        if (cancelled) return;
        setCr(fresh);
        setLoadError(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setLoadError(e instanceof Error ? e.message : "Failed to load request");
      });
    return () => {
      cancelled = true;
    };
  }, [token, id]);

  async function handleWithdraw() {
    if (!token || !cr) return;
    if (
      typeof window !== "undefined" &&
      !window.confirm("Withdraw this change request?")
    ) {
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      await withdrawMyChangeRequest(token, cr.id);
      router.push("/seller/profile/requests");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Withdraw failed");
      setBusy(false);
    }
  }

  if (loadError) {
    return (
      <div className={styles.page}>
        <header className={styles.header}>
          <Link href="/seller/profile/requests" className={styles.backLink}>
            ← Back to requests
          </Link>
        </header>
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

  const open = isOpen(cr);
  const tone = STATUS_TONE[cr.status];

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Link href="/seller/profile/requests" className={styles.backLink}>
          ← Back to requests
        </Link>
      </header>

      <div className={styles.titleRow}>
        <h1 className={styles.title}>{GROUP_LABEL[cr.group]}</h1>
        <span className={`${styles.pill} ${styles[`tone_${tone}`]}`}>
          {cr.status.replace("_", " ")}
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

      {cr.status === "changes_requested" && cr.admin_note && (
        <div className={styles.warnBanner}>
          <strong>Admin asked for changes</strong>
          <p>{cr.admin_note}</p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setEditing(true)}
          >
            Edit and resubmit
          </button>
        </div>
      )}

      {cr.status === "submitted" && (
        <div className={styles.infoBanner}>
          Awaiting admin review. You can withdraw this request at any time.
        </div>
      )}

      {cr.status === "approved" && (
        <div className={styles.successBanner}>
          <strong>Approved.</strong>
          <p>Your profile has been updated with the values shown below.</p>
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

      {actionError && <div className={styles.errorBanner}>{actionError}</div>}

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>What you proposed</h2>
        <ChangeRequestDiffTable
          before={cr.baseline_json}
          after={cr.proposed_json}
          beforeLabel="Current"
          afterLabel="Proposed"
        />
      </section>

      {cr.status === "approved" && cr.applied_json && (
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Applied by admin</h2>
          <ChangeRequestDiffTable
            before={cr.proposed_json}
            after={cr.applied_json}
            beforeLabel="You proposed"
            afterLabel="Applied"
          />
        </section>
      )}

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Timeline</h2>
        <ChangeRequestTimeline events={cr.events} />
      </section>

      {open && (
        <div className={styles.actionRow}>
          <button
            type="button"
            className={styles.withdrawBtn}
            onClick={handleWithdraw}
            disabled={busy}
          >
            {busy ? "Withdrawing…" : "Withdraw request"}
          </button>
        </div>
      )}

      {editing && (
        <ProfileChangeRequestModal
          group={cr.group}
          currentValues={cr.proposed_json}
          open
          onClose={() => setEditing(false)}
          submitLabel="Resubmit"
          onSubmit={async (proposed, note) => {
            if (!token) return;
            await resubmitMyChangeRequest(token, cr.id, { proposed, note });
            await refresh();
          }}
        />
      )}
    </div>
  );
}
