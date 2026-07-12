"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import {
  STATUS_TONE,
  getMyChangeRequest,
  isOpen,
  resubmitMyChangeRequest,
  withdrawMyChangeRequest,
} from "@/lib/changeRequests";
import ChangeRequestDiffTable from "@/components/ChangeRequestDiffTable";
import ChangeRequestTimeline from "@/components/ChangeRequestTimeline";
import ProfileChangeRequestModal from "@/components/ProfileChangeRequestModal";
import type { SellerProfileChangeRequest, Service } from "@/types";
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
  const tCR = useTranslations("Seller.changeRequests");
  const tStatus = useTranslations("Shared.changeRequest");
  const tc = useTranslations("Seller.common");
  const [cr, setCr] = useState<SellerProfileChangeRequest | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [serviceNames, setServiceNames] = useState<Map<number, string>>(
    new Map(),
  );

  useEffect(() => {
    if (cr?.group !== "services") return;
    let cancelled = false;
    get<Service[]>("/api/v1/catalog/services")
      .then((all) => {
        if (cancelled) return;
        setServiceNames(new Map(all.map((s) => [s.id, s.name])));
      })
      .catch(() => {
        // Names fall back to "Service #<id>"; diff still renders.
      });
    return () => {
      cancelled = true;
    };
  }, [cr?.group]);

  const refresh = useCallback(async () => {
    if (!token || !id) return;
    try {
      const fresh = await getMyChangeRequest(token, id);
      setCr(fresh);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : tCR("loadOneError"));
    }
  }, [token, id, tCR]);

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
        setLoadError(e instanceof Error ? e.message : tCR("loadOneError"));
      });
    return () => {
      cancelled = true;
    };
  }, [token, id, tCR]);

  async function handleWithdraw() {
    if (!token || !cr) return;
    if (
      typeof window !== "undefined" &&
      !window.confirm(tCR("withdrawConfirm"))
    ) {
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      await withdrawMyChangeRequest(token, cr.id);
      router.push("/seller/profile/requests");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : tCR("withdrawFailed"));
      setBusy(false);
    }
  }

  if (loadError) {
    return (
      <div className={styles.page}>
        <header className={styles.header}>
          <Link href="/seller/profile/requests" className={styles.backLink}>
            ← {tCR("backToRequests")}
          </Link>
        </header>
        <div className={styles.errorBanner}>{loadError}</div>
      </div>
    );
  }

  if (!cr) {
    return (
      <div className={styles.page}>
        <p className={styles.muted}>{tc("loading")}</p>
      </div>
    );
  }

  const open = isOpen(cr);
  const tone = STATUS_TONE[cr.status];

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Link href="/seller/profile/requests" className={styles.backLink}>
          ← {tCR("backToRequests")}
        </Link>
      </header>

      <div className={styles.titleRow}>
        <h1 className={styles.title}>{tStatus(`group_${cr.group}`)}</h1>
        <span className={`${styles.pill} ${styles[`tone_${tone}`]}`}>
          {tStatus(`status_${cr.status}`)}
        </span>
      </div>

      <p className={styles.meta}>
        {tStatus("status_submitted")}{" "}
        <time dateTime={cr.created_at}>
          {new Date(cr.created_at).toLocaleString()}
        </time>{" "}
        · {tCR("submittedMeta", { count: cr.submission_count })}
      </p>

      {cr.status === "changes_requested" && cr.admin_note && (
        <div className={styles.warnBanner}>
          <strong>{tStatus("kind_changes_requested")}</strong>
          <p>{cr.admin_note}</p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setEditing(true)}
          >
            {tCR("editAndResubmit")}
          </button>
        </div>
      )}

      {cr.status === "submitted" && (
        <div className={styles.infoBanner}>
          {tCR("awaitingReview")}
        </div>
      )}

      {cr.status === "approved" && (
        <div className={styles.successBanner}>
          <strong>{tCR("approvedTitle")}</strong>
          <p>{tCR("approvedBody")}</p>
        </div>
      )}

      {cr.status === "rejected" && (
        <div className={styles.errorBanner}>
          <strong>{tCR("rejectedTitle")}</strong>
          {cr.admin_note && <p>{tCR("rejectedReason", { note: cr.admin_note })}</p>}
        </div>
      )}

      {cr.status === "withdrawn" && (
        <div className={styles.mutedBanner}>{tCR("withdrawnBody")}</div>
      )}

      {actionError && <div className={styles.errorBanner}>{actionError}</div>}

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{tCR("whatProposed")}</h2>
        <ChangeRequestDiffTable
          before={cr.baseline_json}
          after={cr.proposed_json}
          beforeLabel={tCR("diffCurrent")}
          afterLabel={tCR("diffProposed")}
          group={cr.group}
          serviceNames={serviceNames}
        />
      </section>

      {cr.status === "approved" && cr.applied_json && (
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>{tCR("appliedByAdmin")}</h2>
          <ChangeRequestDiffTable
            before={cr.proposed_json}
            after={cr.applied_json}
            beforeLabel={tCR("diffYouProposed")}
            afterLabel={tCR("diffApplied")}
            group={cr.group}
            serviceNames={serviceNames}
          />
        </section>
      )}

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{tCR("timeline")}</h2>
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
            {busy ? "…" : tCR("withdraw")}
          </button>
        </div>
      )}

      {editing && (
        <ProfileChangeRequestModal
          group={cr.group}
          currentValues={cr.proposed_json}
          currentPhone={String(
            (cr.baseline_json as Record<string, unknown>)?.["phone"] ?? "",
          )}
          open
          onClose={() => setEditing(false)}
          submitLabel={tCR("editAndResubmit")}
          onSubmit={async (proposed, note, phoneChangeToken) => {
            if (!token) return;
            await resubmitMyChangeRequest(token, cr.id, {
              proposed,
              note,
              phone_change_token: phoneChangeToken,
            });
            await refresh();
          }}
        />
      )}
    </div>
  );
}
