// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { useAuth } from "@/lib/AuthContext";
import PlanServiceCard from "@/components/seller/PlanServiceCard";
import PaySheet from "@/components/seller/PaySheet";
import {
  applyCreditPpt,
  cancelPlan,
  feeErrorCode,
  getInvoices,
  getMyPlan,
  markInvoicePaid,
  markPaid,
  optIn,
  optInOrderValue,
  optInPpt,
  switchFromPpt,
  topUpPpt,
  type FeeInvoice,
  type SellerPlanView,
} from "@/lib/sellerPlan";
import styles from "./page.module.css";

const ERROR_MESSAGES: Record<string, string> = {
  subscription_not_offerable: "This plan isn't available right now.",
  plan_not_available: "That plan duration isn't offered.",
  payment_already_pending: "You already have a payment awaiting review.",
  no_pending_payment: "There's no pending payment to confirm.",
  below_min_deposit: "Deposit is below the minimum for this service.",
  pay_per_txn_not_offerable: "Pay-per-order isn't available for this service.",
  order_value_not_offerable: "Order Value % isn't available for this service.",
  invoice_not_found: "That invoice couldn't be found.",
  invoice_not_payable: "That invoice is already settled.",
  amount_exceeds_credit: "That's more than your available wallet credit.",
  no_credit_available: "You have no wallet credit to apply.",
  balance_negative: "Settle the outstanding balance before switching plans.",
  bad_amount: "Enter a valid amount.",
};

function messageFor(code: string | null): string {
  return (code && ERROR_MESSAGES[code]) || "Something went wrong. Please try again.";
}

/** A pending pay-sheet request raised by a card action. */
interface PaySheetReq {
  serviceId: number;
  title: string;
  amount: number | null;
  amountEditable?: boolean;
  confirm: (opts: { amount: number; note: string | null }) => Promise<unknown>;
}

export default function SellerPlanPage() {
  const { token } = useAuth();
  const [data, setData] = useState<SellerPlanView | null>(null);
  const [invoices, setInvoices] = useState<Record<number, FeeInvoice[]>>({});
  const [fetching, setFetching] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyService, setBusyService] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [paySheet, setPaySheet] = useState<PaySheetReq | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setFetching(true);
    setLoadError(null);
    try {
      const plan = await getMyPlan(token);
      setData(plan);
      // Fetch invoices for each Order Value % service (best-effort per service).
      const ovServices = plan.services.filter((s) => s.model === "order_value_percent");
      const entries = await Promise.all(
        ovServices.map(async (s) => {
          try {
            return [s.service_id, await getInvoices(s.service_id, token)] as const;
          } catch {
            return [s.service_id, [] as FeeInvoice[]] as const;
          }
        }),
      );
      setInvoices(Object.fromEntries(entries));
    } catch {
      setLoadError("Couldn't load your plan. Please refresh.");
    } finally {
      setFetching(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(serviceId: number, fn: () => Promise<unknown>) {
    setBusyService(serviceId);
    setActionError(null);
    try {
      await fn();
      await load();
    } catch (err) {
      setActionError(messageFor(feeErrorCode(err)));
    } finally {
      setBusyService(null);
    }
  }

  const svcName = (id: number) => data?.services.find((s) => s.service_id === id)?.service_name ?? "";

  // ── Pay-sheet openers (each raises the unified sheet) ────────────────
  const onSubscribe = (serviceId: number, duration: number, price: number) =>
    setPaySheet({
      serviceId,
      title: `Subscribe · ${svcName(serviceId)} · ${duration} months`,
      amount: price,
      confirm: async ({ note }) => {
        await optIn(serviceId, duration, token);
        await markPaid(serviceId, note, token);
      },
    });

  const onStartOrderValue = (serviceId: number, deposit: number) =>
    setPaySheet({
      serviceId,
      title: `Security deposit · ${svcName(serviceId)}`,
      amount: deposit,
      confirm: async ({ note }) => {
        await optInOrderValue(serviceId, deposit, token);
        await markPaid(serviceId, note, token);
      },
    });

  const onStartPpt = (serviceId: number, deposit: number) =>
    setPaySheet({
      serviceId,
      title: `Deposit · ${svcName(serviceId)}`,
      amount: deposit,
      confirm: async ({ note }) => {
        await optInPpt(serviceId, deposit, false, token);
        await markPaid(serviceId, note, token);
      },
    });

  const onTopUp = (serviceId: number) =>
    setPaySheet({
      serviceId,
      title: `Top up · ${svcName(serviceId)}`,
      amount: null,
      amountEditable: true,
      confirm: async ({ amount, note }) => {
        await topUpPpt(serviceId, amount, token);
        await markPaid(serviceId, note, token);
      },
    });

  const onPayInvoice = (serviceId: number, invoiceId: number, amount: number) =>
    setPaySheet({
      serviceId,
      title: `Invoice payment · ${svcName(serviceId)}`,
      amount,
      confirm: async () => {
        await markInvoicePaid(serviceId, invoiceId, token);
      },
    });

  async function handleSheetConfirm(opts: { amount: number; note: string | null }) {
    if (!paySheet) return;
    const req = paySheet;
    setBusyService(req.serviceId);
    setActionError(null);
    try {
      await req.confirm(opts);
      setPaySheet(null);
      await load();
    } catch (err) {
      setActionError(messageFor(feeErrorCode(err)));
    } finally {
      setBusyService(null);
    }
  }

  // ── Direct actions (no offline payment) ──────────────────────────────
  const onCancel = (serviceId: number) => {
    if (
      !window.confirm(
        "Cancel this subscription? It stays active until the end of the paid term, then stops renewing.",
      )
    ) {
      return;
    }
    void run(serviceId, () => cancelPlan(serviceId, token));
  };

  const onStartPptWithCredit = (serviceId: number, deposit: number) =>
    void run(serviceId, () => optInPpt(serviceId, deposit, true, token));

  const onApplyCredit = (serviceId: number, amount: number) =>
    void run(serviceId, () => applyCreditPpt(serviceId, amount, token));

  const onStopPpt = (serviceId: number) => {
    if (
      !window.confirm(
        "Leave pay-per-order? Any positive balance is moved to your store wallet credit. A negative balance must be settled first.",
      )
    ) {
      return;
    }
    void run(serviceId, () => switchFromPpt(serviceId, token));
  };

  return (
    <div className={styles.page}>
      <div className={styles.head}>
        <div>
          <h1 className={styles.title}>Plan &amp; Billing</h1>
          <p className={styles.subtitle}>Manage your store&apos;s platform-fee plan for each service.</p>
        </div>
        <Link href="/seller/plan/faq" className={styles.faqLink}>
          Read the FAQ →
        </Link>
      </div>

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
      ) : !data || data.services.length === 0 ? (
        <div className={styles.empty}>No services on your store yet.</div>
      ) : (
        <div className={styles.list}>
          {data.services.map((s) => (
            <PlanServiceCard
              key={s.service_id}
              service={s}
              busy={busyService === s.service_id}
              feeCredit={data.fee_credit_balance}
              invoices={invoices[s.service_id]}
              onSubscribe={onSubscribe}
              onStartOrderValue={onStartOrderValue}
              onStartPpt={onStartPpt}
              onTopUp={onTopUp}
              onPayInvoice={onPayInvoice}
              onCancel={onCancel}
              onStartPptWithCredit={onStartPptWithCredit}
              onApplyCredit={onApplyCredit}
              onStopPpt={onStopPpt}
            />
          ))}
        </div>
      )}

      {paySheet && data && (
        <PaySheet
          open
          title={paySheet.title}
          amount={paySheet.amount}
          amountEditable={paySheet.amountEditable}
          payment={data.payment_details}
          busy={busyService === paySheet.serviceId}
          onConfirm={handleSheetConfirm}
          onClose={() => setPaySheet(null)}
        />
      )}
    </div>
  );
}
