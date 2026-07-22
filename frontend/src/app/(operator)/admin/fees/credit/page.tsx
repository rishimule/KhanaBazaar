// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/lib/AuthContext";
import DataTable, { type Column } from "@/components/DataTable";
import Modal from "@/components/Modal";
import {
  adjustStoreCredit,
  cashOutStoreCredit,
  feeErrorCode,
  grantStoreCredit,
  listStoreCredit,
  type StoreCreditView,
} from "@/lib/adminFees";
import styles from "./page.module.css";

type Action = "grant" | "adjust" | "cash_out";

const ACTION_META: Record<Action, { title: string; confirm: string; hint: string; signed: boolean }> = {
  grant: {
    title: "Grant wallet credit",
    confirm: "Grant credit",
    hint: "Add goodwill credit to this store. It auto-applies to future fee obligations.",
    signed: false,
  },
  adjust: {
    title: "Adjust wallet credit",
    confirm: "Apply adjustment",
    hint: "Correct the balance up or down (use a negative amount to reduce). Result cannot go below zero.",
    signed: true,
  },
  cash_out: {
    title: "Cash out wallet credit",
    confirm: "Record cash-out",
    hint: "Records a refund of unused credit; settle the actual transfer offline via UPI/bank.",
    signed: false,
  },
};

const ERR: Record<string, string> = {
  bad_amount: "Enter a valid amount within the available balance.",
  negative_balance: "That would drive the balance below zero.",
  zero_amount: "Enter a non-zero amount.",
  store_not_found: "Store not found.",
};

function rupees(n: number): string {
  return `₹${n.toLocaleString("en-IN")}`;
}

export default function AdminFeeCreditPage() {
  const { token } = useAuth();
  const [rows, setRows] = useState<StoreCreditView[]>([]);
  const [fetching, setFetching] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [target, setTarget] = useState<{ store: StoreCreditView; action: Action } | null>(null);
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    if (!token) return;
    setFetching(true);
    setLoadError(null);
    try {
      setRows(await listStoreCredit(token));
    } catch {
      setLoadError("Couldn't load the wallet-credit worklist.");
    } finally {
      setFetching(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  function open(store: StoreCreditView, action: Action) {
    setTarget({ store, action });
    setAmount("");
    setReason("");
    setActionError(null);
  }

  async function submit() {
    if (!target) return;
    const amt = Number(amount);
    if (!Number.isFinite(amt) || amt === 0) {
      setActionError("Enter a valid amount.");
      return;
    }
    if (reason.trim().length < 10) {
      setActionError("Reason must be at least 10 characters.");
      return;
    }
    const { store, action } = target;
    setBusy(true);
    setActionError(null);
    try {
      if (action === "grant") await grantStoreCredit(token, store.store_id, amt, reason.trim());
      else if (action === "adjust") await adjustStoreCredit(token, store.store_id, amt, reason.trim());
      else await cashOutStoreCredit(token, store.store_id, amt, reason.trim());
      setTarget(null);
      await load();
    } catch (err) {
      setActionError(ERR[feeErrorCode(err) ?? ""] ?? "Couldn't apply that change.");
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<StoreCreditView>[] = [
    { key: "store", label: "Store", render: (r) => r.store_name },
    {
      key: "balance",
      label: "Wallet credit",
      render: (r) => (
        <span className={r.fee_credit_balance < 0 ? styles.negative : styles.positive}>
          {r.fee_credit_balance < 0
            ? `owes ${rupees(Math.abs(r.fee_credit_balance))}`
            : rupees(r.fee_credit_balance)}
        </span>
      ),
    },
    {
      key: "actions",
      label: "",
      render: (r) => (
        <span className={styles.actions}>
          <button type="button" className="btn" disabled={busy} onClick={() => open(r, "grant")}>
            Grant
          </button>
          <button type="button" className="btn" disabled={busy} onClick={() => open(r, "adjust")}>
            Adjust
          </button>
          <button
            type="button"
            className="btn"
            disabled={busy || r.fee_credit_balance <= 0}
            onClick={() => open(r, "cash_out")}
          >
            Cash out
          </button>
        </span>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <p className={styles.intro}>
        Store wallet credit is platform-held money owed back to sellers (from leaving a paid plan,
        or admin goodwill). Positive balances are refundable via cash-out or auto-applied to future
        fees; a debt is recorded from a negative arrangement balance on exit (best-effort collection).
      </p>

      {actionError && !target && (
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
          data={rows}
          keyField="store_id"
          emptyMessage="No stores with wallet credit."
          mobileCardRender={(r) => (
            <div className={styles.card}>
              <div className={styles.cardTop}>
                <strong>{r.store_name}</strong>
                <span className={r.fee_credit_balance < 0 ? styles.negative : styles.positive}>
                  {r.fee_credit_balance < 0
                    ? `owes ${rupees(Math.abs(r.fee_credit_balance))}`
                    : rupees(r.fee_credit_balance)}
                </span>
              </div>
              <div className={styles.actions}>
                <button type="button" className="btn" disabled={busy} onClick={() => open(r, "grant")}>Grant</button>
                <button type="button" className="btn" disabled={busy} onClick={() => open(r, "adjust")}>Adjust</button>
                <button type="button" className="btn" disabled={busy || r.fee_credit_balance <= 0} onClick={() => open(r, "cash_out")}>Cash out</button>
              </div>
            </div>
          )}
        />
      )}

      {target && (
        <Modal
          title={`${ACTION_META[target.action].title} — ${target.store.store_name}`}
          onClose={() => setTarget(null)}
          footer={
            <>
              <button type="button" className="btn" disabled={busy} onClick={() => setTarget(null)}>
                Cancel
              </button>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={submit}>
                {ACTION_META[target.action].confirm}
              </button>
            </>
          }
        >
          <p className={styles.intro}>{ACTION_META[target.action].hint}</p>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="credit-amount">
              Amount (₹){ACTION_META[target.action].signed ? " — negative to reduce" : ""}
            </label>
            <input
              id="credit-amount"
              type="number"
              inputMode="numeric"
              className={styles.input}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="e.g. 100"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="credit-reason">
              Reason (required, ≥10 chars — audited)
            </label>
            <textarea
              id="credit-reason"
              className={styles.textarea}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={500}
              placeholder="Why is this change being made?"
            />
          </div>
          {actionError && (
            <div className={styles.errorBanner} role="alert">
              {actionError}
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}
