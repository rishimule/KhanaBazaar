// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { use, useCallback, useEffect, useState } from "react";

import { useAuth } from "@/lib/AuthContext";
import Modal from "@/components/Modal";
import { fetchSellerHub } from "@/lib/adminActions";
import {
  getStoreArrangements,
  extendArrangement,
  terminateArrangement,
  compArrangement,
  feeErrorCode,
  type ArrangementSummary,
} from "@/lib/adminFees";
import styles from "./page.module.css";

const MODEL_LABEL: Record<string, string> = {
  freebie: "Free trial",
  subscription: "Subscription",
  order_value_percent: "Order-value %",
  pay_per_transaction: "Pay per order",
};

const STATUS_PILL: Record<string, { label: string; kind: string }> = {
  trial: { label: "Trial", kind: "neutral" },
  active: { label: "Active", kind: "member" },
  grace: { label: "Grace", kind: "warning" },
  suspended: { label: "Suspended", kind: "sale" },
  pending_activation: { label: "Pending", kind: "warning" },
};

const ERROR_MESSAGES: Record<string, string> = {
  seller_not_active: "This seller isn't approved, so fee arrangements can't be changed.",
  arrangement_not_found: "That arrangement no longer exists.",
  store_not_found: "Store not found.",
  seller_not_found: "Seller not found.",
};

type ActionType = "extend" | "terminate" | "comp";

export default function AdminSellerFeesPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { token } = useAuth();
  const [storeId, setStoreId] = useState<number | null>(null);
  const [noStore, setNoStore] = useState(false);
  const [rows, setRows] = useState<ArrangementSummary[]>([]);
  const [fetching, setFetching] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [action, setAction] = useState<{ type: ActionType; arr: ArrangementSummary } | null>(null);
  const [days, setDays] = useState(30);
  const [months, setMonths] = useState(3);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadRows = useCallback(
    async (sid: number) => {
      if (!token) return;
      setFetching(true);
      try {
        setRows(await getStoreArrangements(token, sid));
      } catch {
        setLoadError("Couldn't load fee arrangements.");
      } finally {
        setFetching(false);
      }
    },
    [token],
  );

  useEffect(() => {
    if (!token) return;
    fetchSellerHub(Number(id), token)
      .then((hub) => {
        if (hub.store_id == null) {
          setNoStore(true);
          setFetching(false);
          return;
        }
        setStoreId(hub.store_id);
        void loadRows(hub.store_id);
      })
      .catch(() => {
        setLoadError("Couldn't load this seller.");
        setFetching(false);
      });
  }, [id, token, loadRows]);

  function openAction(type: ActionType, arr: ArrangementSummary) {
    setAction({ type, arr });
    setDays(30);
    setMonths(3);
    setReason("");
    setActionError(null);
  }

  async function submitAction() {
    if (!action || !token || storeId == null) return;
    const { type, arr } = action;
    if (type === "terminate" && reason.trim().length < 1) {
      setActionError("A reason is required to terminate.");
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      const note = reason.trim() || undefined;
      if (type === "extend") await extendArrangement(token, arr.id, days, note);
      else if (type === "comp") await compArrangement(token, arr.id, months, note);
      else await terminateArrangement(token, arr.id, reason.trim());
      setAction(null);
      await loadRows(storeId);
    } catch (err) {
      const code = feeErrorCode(err);
      setActionError((code && ERROR_MESSAGES[code]) || "Action failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  if (noStore) return <div className={styles.empty}>This seller has no store provisioned yet.</div>;
  if (fetching) return <div className={styles.loader}>Loading…</div>;
  if (loadError) return <div className={styles.errorBanner} role="alert">{loadError}</div>;

  const actionTitle =
    action?.type === "extend" ? "Extend arrangement"
      : action?.type === "comp" ? "Comp (grant) subscription"
        : "Terminate arrangement";

  return (
    <div className={styles.page}>
      <h2 className={styles.title}>Fee arrangements</h2>
      <p className={styles.intro}>
        Admin overrides per (store, service). Actions are audit-logged and notify the seller.
      </p>

      {rows.length === 0 ? (
        <div className={styles.empty}>No fee arrangements for this store.</div>
      ) : (
        <div className={styles.list}>
          {rows.map((r) => {
            const pill = STATUS_PILL[r.status] ?? { label: r.status, kind: "neutral" };
            return (
              <div key={r.id} className={styles.row}>
                <div className={styles.rowMain}>
                  <span className={styles.service}>{r.service_name}</span>
                  <span className={`badge badge--${pill.kind}`}>{pill.label}</span>
                  <span className={styles.model}>{MODEL_LABEL[r.model] ?? r.model}</span>
                </div>
                <div className={styles.rowMeta}>
                  {r.valid_until ? `Valid until ${r.valid_until}` : "No expiry"}
                  {r.cancel_requested ? " · cancelling" : ""}
                  {r.pending ? " · payment pending" : ""}
                </div>
                <div className={styles.rowActions}>
                  <button type="button" className={styles.actionBtn} onClick={() => openAction("extend", r)}>Extend</button>
                  <button type="button" className={styles.actionBtn} onClick={() => openAction("comp", r)}>Comp</button>
                  <button type="button" className={styles.terminateBtn} onClick={() => openAction("terminate", r)}>Terminate</button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {action && (
        <Modal
          title={actionTitle}
          onClose={() => setAction(null)}
          footer={
            <div className={styles.modalFooter}>
              <button type="button" className={styles.cancelBtn} onClick={() => setAction(null)} disabled={busy}>Cancel</button>
              <button type="button" className="btn btn-primary" onClick={submitAction} disabled={busy}>
                {action.type === "terminate" ? "Terminate" : "Confirm"}
              </button>
            </div>
          }
        >
          <p className={styles.modalService}>
            {action.arr.service_name} · {MODEL_LABEL[action.arr.model] ?? action.arr.model}
          </p>
          {action.type === "extend" && (
            <label className={styles.field}>
              <span>Extend by (days)</span>
              <input type="number" min={1} max={3650} value={days}
                onChange={(e) => { const n = Number(e.target.value); setDays(Number.isNaN(n) ? 1 : n); }} />
            </label>
          )}
          {action.type === "comp" && (
            <label className={styles.field}>
              <span>Duration (months)</span>
              <input type="number" min={1} max={60} value={months}
                onChange={(e) => { const n = Number(e.target.value); setMonths(Number.isNaN(n) ? 1 : n); }} />
            </label>
          )}
          <label className={styles.field}>
            <span>{action.type === "terminate" ? "Reason (required)" : "Reason (optional)"}</span>
            <textarea maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder="Shown in the audit log and seller notification" />
          </label>
          {actionError && <p className={styles.modalError} role="alert">{actionError}</p>}
        </Modal>
      )}
    </div>
  );
}
