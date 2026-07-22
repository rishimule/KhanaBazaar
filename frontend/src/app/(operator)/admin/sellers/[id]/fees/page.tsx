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
  switchArrangement,
  getArrangementInvoices,
  forfeitDeposit,
  refundDeposit,
  feeErrorCode,
  type ArrangementSummary,
  type FeeInvoice,
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
  duration_required: "Pick a subscription duration.",
  bad_target_model: "Unsupported target plan.",
  unsupported_target_model: "Unsupported target plan.",
  bad_forfeit_amount: "Enter an amount between ₹0 and the held deposit.",
  refund_requires_exit: "Terminate the arrangement before refunding the deposit.",
  not_order_value: "This action only applies to an Order Value % arrangement.",
};

type ActionType = "extend" | "terminate" | "comp" | "switch" | "invoices" | "forfeit" | "refund";

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
  const [targetModel, setTargetModel] = useState("subscription");
  const [disposition, setDisposition] = useState("credit");
  const [reason, setReason] = useState("");
  const [forfeitAmount, setForfeitAmount] = useState("");
  const [refundMode, setRefundMode] = useState<"offline" | "credit">("offline");
  const [invoiceRows, setInvoiceRows] = useState<FeeInvoice[]>([]);
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
    setTargetModel("subscription");
    setDisposition("credit");
    setReason("");
    setForfeitAmount("");
    setRefundMode("offline");
    setInvoiceRows([]);
    setActionError(null);
    if (type === "invoices" && token) {
      getArrangementInvoices(token, arr.id)
        .then(setInvoiceRows)
        .catch(() => setActionError("Couldn't load invoices."));
    }
  }

  async function submitAction() {
    if (!action || !token || storeId == null) return;
    const { type, arr } = action;
    if (type === "terminate" && reason.trim().length < 1) {
      setActionError("A reason is required to terminate.");
      return;
    }
    if (type === "switch" && reason.trim().length < 10) {
      setActionError("A reason of at least 10 characters is required to switch.");
      return;
    }
    if (type === "forfeit" && reason.trim().length < 10) {
      setActionError("A reason of at least 10 characters is required to forfeit.");
      return;
    }
    if (type === "forfeit" && !(Number(forfeitAmount) > 0)) {
      setActionError("Enter the amount to forfeit.");
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      const note = reason.trim() || undefined;
      if (type === "extend") await extendArrangement(token, arr.id, days, note);
      else if (type === "comp") await compArrangement(token, arr.id, months, note);
      else if (type === "switch")
        await switchArrangement(token, arr.id, targetModel, reason.trim(), {
          durationMonths: targetModel === "subscription" ? months : undefined,
          disposition,
        });
      else if (type === "forfeit")
        await forfeitDeposit(token, arr.id, Number(forfeitAmount), reason.trim());
      else if (type === "refund")
        await refundDeposit(token, arr.id, refundMode, note);
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
        : action?.type === "switch" ? "Force-switch plan"
          : action?.type === "invoices" ? "Order Value % invoices"
            : action?.type === "forfeit" ? "Forfeit security deposit"
              : action?.type === "refund" ? "Refund security deposit"
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
                  {r.model === "order_value_percent" && (
                    <>
                      <button type="button" className={styles.actionBtn} onClick={() => openAction("invoices", r)}>Invoices</button>
                      <button type="button" className={styles.actionBtn} onClick={() => openAction("forfeit", r)}>Forfeit</button>
                      <button type="button" className={styles.actionBtn} onClick={() => openAction("refund", r)}>Refund</button>
                    </>
                  )}
                  <button type="button" className={styles.actionBtn} onClick={() => openAction("extend", r)}>Extend</button>
                  <button type="button" className={styles.actionBtn} onClick={() => openAction("comp", r)}>Comp</button>
                  <button type="button" className={styles.actionBtn} onClick={() => openAction("switch", r)}>Switch</button>
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
            action.type === "invoices" ? (
              <div className={styles.modalFooter}>
                <button type="button" className="btn btn-primary" onClick={() => setAction(null)}>Close</button>
              </div>
            ) : (
              <div className={styles.modalFooter}>
                <button type="button" className={styles.cancelBtn} onClick={() => setAction(null)} disabled={busy}>Cancel</button>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={submitAction}
                  disabled={
                    busy ||
                    (action.type === "terminate" && !reason.trim()) ||
                    (action.type === "switch" && reason.trim().length < 10) ||
                    (action.type === "forfeit" && (reason.trim().length < 10 || !(Number(forfeitAmount) > 0)))
                  }
                >
                  {action.type === "terminate" ? "Terminate"
                    : action.type === "switch" ? "Switch plan"
                      : action.type === "forfeit" ? "Forfeit"
                        : action.type === "refund" ? "Refund deposit"
                          : "Confirm"}
                </button>
              </div>
            )
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
          {action.type === "switch" && (
            <>
              <label className={styles.field}>
                <span>Target plan</span>
                <select value={targetModel} onChange={(e) => setTargetModel(e.target.value)}>
                  <option value="subscription">Subscription</option>
                  <option value="freebie">Free trial (freebie)</option>
                </select>
              </label>
              {targetModel === "subscription" && (
                <label className={styles.field}>
                  <span>Subscription duration (months)</span>
                  <input type="number" min={1} max={60} value={months}
                    onChange={(e) => { const n = Number(e.target.value); setMonths(Number.isNaN(n) ? 1 : n); }} />
                </label>
              )}
              <label className={styles.field}>
                <span>Leftover pay-per-order balance</span>
                <select value={disposition} onChange={(e) => setDisposition(e.target.value)}>
                  <option value="credit">Move to wallet credit</option>
                  <option value="cash_out">Cash out (record refund)</option>
                  <option value="waive">Waive debt (write off a negative balance)</option>
                </select>
              </label>
            </>
          )}
          {action.type === "invoices" && (
            invoiceRows.length === 0 ? (
              <p className={styles.modalService}>No invoices yet.</p>
            ) : (
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {invoiceRows.map((inv) => (
                  <li key={inv.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 0", borderTop: "1px solid var(--color-border-divider, #EAEAEA)" }}>
                    <span style={{ flex: 1 }}>{inv.period_start.slice(0, 7)}</span>
                    <span>₹{inv.sales_total.toLocaleString("en-IN")}</span>
                    <span>₹{inv.amount_due.toLocaleString("en-IN")}</span>
                    <span className={`badge badge--${inv.status === "paid" ? "member" : inv.status === "overdue" ? "sale" : inv.status === "pending" ? "warning" : "neutral"}`}>{inv.status}</span>
                  </li>
                ))}
              </ul>
            )
          )}
          {action.type === "forfeit" && (
            <label className={styles.field}>
              <span>Amount to forfeit (₹)</span>
              <input type="number" min={0} value={forfeitAmount}
                onChange={(e) => setForfeitAmount(e.target.value)}
                placeholder="Applied against outstanding invoices" />
            </label>
          )}
          {action.type === "refund" && (
            <label className={styles.field}>
              <span>Refund via</span>
              <select value={refundMode} onChange={(e) => setRefundMode(e.target.value as "offline" | "credit")}>
                <option value="offline">Offline (UPI/bank — recorded only)</option>
                <option value="credit">Store wallet credit</option>
              </select>
            </label>
          )}
          {action.type !== "invoices" && (
            <label className={styles.field}>
              <span>
                {action.type === "terminate"
                  ? "Reason (required)"
                  : action.type === "switch"
                    ? "Reason (required, ≥10 chars)"
                    : action.type === "forfeit"
                      ? "Reason (required, ≥10 chars)"
                      : action.type === "refund"
                        ? "Note (optional)"
                        : "Reason (optional)"}
              </span>
              <textarea maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)}
                placeholder="Shown in the audit log and seller notification" />
            </label>
          )}
          {actionError && <p className={styles.modalError} role="alert">{actionError}</p>}
        </Modal>
      )}
    </div>
  );
}
