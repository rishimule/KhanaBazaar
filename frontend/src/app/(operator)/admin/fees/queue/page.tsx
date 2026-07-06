// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/lib/AuthContext";
import DataTable, { type Column } from "@/components/DataTable";
import AdminReasonModal from "@/components/admin/AdminReasonModal";
import {
  getFeeQueue,
  confirmFeePayment,
  rejectFeePayment,
  type PaymentQueueItem,
} from "@/lib/adminFees";
import styles from "./page.module.css";

const KIND_LABEL: Record<string, string> = {
  subscription_fee: "Subscription fee",
  SubscriptionFee: "Subscription fee",
  security_deposit: "Security deposit",
  SecurityDeposit: "Security deposit",
  pay_per_txn_topup: "Balance top-up",
  PayPerTxnTopUp: "Balance top-up",
  order_value_invoice: "Order-value invoice",
  OrderValueInvoice: "Order-value invoice",
};

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export default function AdminFeeQueuePage() {
  const { token } = useAuth();
  const [items, setItems] = useState<PaymentQueueItem[]>([]);
  const [fetching, setFetching] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [rejectTarget, setRejectTarget] = useState<PaymentQueueItem | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setFetching(true);
    setLoadError(null);
    try {
      setItems(await getFeeQueue(token));
    } catch {
      setLoadError("Couldn't load the confirmation queue.");
    } finally {
      setFetching(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleConfirm(item: PaymentQueueItem) {
    setBusyId(item.payment_id);
    setActionError(null);
    try {
      await confirmFeePayment(token, item.payment_id);
      await load();
    } catch {
      setActionError("Couldn't confirm that payment. It may have already been handled.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleReject(reason: string) {
    if (!rejectTarget) return;
    try {
      await rejectFeePayment(token, rejectTarget.payment_id, reason);
      setRejectTarget(null);
      await load();
    } catch {
      setActionError("Couldn't reject that payment. It may have already been handled.");
      setRejectTarget(null);
    }
  }

  const columns: Column<PaymentQueueItem>[] = [
    { key: "store", label: "Store", render: (r) => r.store_name },
    { key: "service", label: "Service", render: (r) => r.service_name },
    { key: "kind", label: "Kind", render: (r) => KIND_LABEL[r.kind] ?? r.kind },
    {
      key: "amount",
      label: "Amount",
      render: (r) => `₹${r.amount.toLocaleString("en-IN")}`,
    },
    { key: "note", label: "Seller note", render: (r) => r.seller_note || "—" },
    {
      key: "since",
      label: "Pending since",
      render: (r) => fmtDate(r.pending_since ?? r.created_at),
    },
    {
      key: "actions",
      label: "",
      render: (r) => (
        <span className={styles.actions}>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busyId === r.payment_id}
            onClick={() => handleConfirm(r)}
          >
            Confirm
          </button>
          <button
            type="button"
            className={styles.rejectBtn}
            disabled={busyId === r.payment_id}
            onClick={() => setRejectTarget(r)}
          >
            Reject
          </button>
        </span>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <p className={styles.intro}>
        Offline fee payments awaiting confirmation. Confirming activates the seller&apos;s plan.
      </p>

      {actionError && (
        <div className={styles.errorBanner} role="alert">
          {actionError}
        </div>
      )}

      {fetching ? (
        <div className={styles.loader}>Loading…</div>
      ) : loadError ? (
        <div className={styles.errorBanner} role="alert">
          {loadError}
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={items}
          keyField="payment_id"
          emptyMessage="No payments awaiting confirmation."
          mobileCardRender={(r) => (
            <div className={styles.card}>
              <div className={styles.cardTop}>
                <strong>{r.store_name}</strong>
                <span>₹{r.amount.toLocaleString("en-IN")}</span>
              </div>
              <div className={styles.cardMeta}>
                {r.service_name} · {KIND_LABEL[r.kind] ?? r.kind} · {fmtDate(r.pending_since ?? r.created_at)}
              </div>
              {r.seller_note && <div className={styles.cardNote}>“{r.seller_note}”</div>}
              <div className={styles.actions}>
                <button type="button" className="btn btn-primary" disabled={busyId === r.payment_id} onClick={() => handleConfirm(r)}>
                  Confirm
                </button>
                <button type="button" className={styles.rejectBtn} disabled={busyId === r.payment_id} onClick={() => setRejectTarget(r)}>
                  Reject
                </button>
              </div>
            </div>
          )}
        />
      )}

      {rejectTarget && (
        <AdminReasonModal
          title={`Reject payment from ${rejectTarget.store_name}`}
          description="The seller will be notified. Explain why this payment can't be confirmed."
          confirmLabel="Reject payment"
          onConfirm={handleReject}
          onClose={() => setRejectTarget(null)}
        />
      )}
    </div>
  );
}
