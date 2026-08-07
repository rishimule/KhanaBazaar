// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { useAuth } from "@/lib/AuthContext";
import PlanExitConfirmModal from "@/components/seller/PlanExitConfirmModal";
import PlanServiceCard from "@/components/seller/PlanServiceCard";
import PaySheet from "@/components/seller/PaySheet";
import {
  applyCreditPpt,
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

/** Amount for interpolation into a `Plan` message that already carries `₹`.
 *  Matches PlanServiceCard's `rupees()` grouping; drops a trailing `.0` so a
 *  whole-rupee balance never renders as "120.5"-style noise. */
function money(n: number): string {
  return n.toLocaleString("en-IN", { maximumFractionDigits: 2 });
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
  const t = useTranslations("Plan");
  const [data, setData] = useState<SellerPlanView | null>(null);
  const [invoices, setInvoices] = useState<Record<number, FeeInvoice[]>>({});
  const [fetching, setFetching] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyService, setBusyService] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [paySheet, setPaySheet] = useState<PaySheetReq | null>(null);
  const [sheetError, setSheetError] = useState<string | null>(null);
  const [pptExit, setPptExit] = useState<{
    serviceId: number;
    serviceName: string;
    balance: number;
    /** One order fee — the threshold `_evaluate_ppt_status` reactivates at. */
    fee: number;
  } | null>(null);
  const [pptExitError, setPptExitError] = useState<string | null>(null);

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

  const openSheet = (req: PaySheetReq) => {
    setSheetError(null);
    setPaySheet(req);
  };

  // ── Pay-sheet openers (each raises the unified sheet) ────────────────
  // A blank note is a no-op on the backend, so mark-paid is skipped when the
  // seller leaves the reference empty (keeps confirm a single request).
  const onSubscribe = (serviceId: number, duration: number, price: number) =>
    openSheet({
      serviceId,
      title: `Subscribe · ${svcName(serviceId)} · ${duration} months`,
      amount: price,
      confirm: async ({ note }) => {
        await optIn(serviceId, duration, token);
        if (note) await markPaid(serviceId, note, token);
      },
    });

  const onStartOrderValue = (serviceId: number, deposit: number) =>
    openSheet({
      serviceId,
      title: `Security deposit · ${svcName(serviceId)}`,
      amount: deposit,
      confirm: async ({ note }) => {
        await optInOrderValue(serviceId, deposit, token);
        if (note) await markPaid(serviceId, note, token);
      },
    });

  const onStartPpt = (serviceId: number, deposit: number) =>
    openSheet({
      serviceId,
      title: `Deposit · ${svcName(serviceId)}`,
      amount: deposit,
      confirm: async ({ note }) => {
        await optInPpt(serviceId, deposit, false, token);
        if (note) await markPaid(serviceId, note, token);
      },
    });

  const onTopUp = (serviceId: number) =>
    openSheet({
      serviceId,
      title: `Top up · ${svcName(serviceId)}`,
      amount: null,
      amountEditable: true,
      confirm: async ({ amount, note }) => {
        await topUpPpt(serviceId, amount, token);
        if (note) await markPaid(serviceId, note, token);
      },
    });

  const onPayInvoice = (serviceId: number, invoiceId: number, amount: number) =>
    openSheet({
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
    setSheetError(null);
    let ok = false;
    try {
      await req.confirm(opts);
      ok = true;
    } catch (err) {
      // Show the error inside the sheet, where the seller is looking.
      setSheetError(messageFor(feeErrorCode(err)));
    } finally {
      setBusyService(null);
      // Refresh even after a partial failure — the opt-in step may have landed.
      await load();
    }
    if (ok) setPaySheet(null);
  }

  // ── Direct actions (no offline payment) ──────────────────────────────
  const onStartPptWithCredit = (serviceId: number, deposit: number) =>
    void run(serviceId, () => optInPpt(serviceId, deposit, true, token));

  const onApplyCredit = (serviceId: number, amount: number) =>
    void run(serviceId, () => applyCreditPpt(serviceId, amount, token));

  // Stopping pay-per-order hides the service from every customer surface, so
  // it gets a disclosed modal, never a window.confirm (audit BLOCKER #8).
  const onStopPpt = (serviceId: number) => {
    const svc = data?.services.find((s) => s.service_id === serviceId);
    setPptExitError(null);
    setPptExit({
      serviceId,
      serviceName: svc?.service_name ?? "",
      balance: svc?.balance ?? 0,
      fee: svc?.pay_per_txn_fee ?? 0,
    });
  };

  // Mirrors handleSheetConfirm: hold the surface open on failure so the error
  // lands where the seller is looking, not in a page banner they scrolled past.
  async function handlePptExitConfirm() {
    if (!pptExit) return;
    const req = pptExit;
    setBusyService(req.serviceId);
    setPptExitError(null);
    let ok = false;
    try {
      await switchFromPpt(req.serviceId, token);
      ok = true;
    } catch (err) {
      setPptExitError(messageFor(feeErrorCode(err)));
    } finally {
      setBusyService(null);
      await load();
    }
    if (ok) setPptExit(null);
  }

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
          error={sheetError}
          onConfirm={handleSheetConfirm}
          onClose={() => {
            setSheetError(null);
            setPaySheet(null);
          }}
        />
      )}

      {pptExit && (
        <PlanExitConfirmModal
          title={t("exitPptTitle")}
          consequence={t("exitPptConsequence", { service: pptExit.serviceName })}
          // Three real money states, not two: the backend refuses the exit
          // outright on a negative balance (FeeError "balance_negative"), so
          // saying "no balance left to move" there would be false.
          money={
            pptExit.balance < 0
              ? t("exitPptMoneyNegative", { amount: money(-pptExit.balance) })
              : pptExit.balance > 0
                ? t("exitPptMoney", { amount: money(pptExit.balance) })
                : t("exitPptMoneyNone")
          }
          // The undo is only *immediate* once the balance clears one order fee —
          // `_evaluate_ppt_status` reactivates on `balance >= fee`, not `> 0`. A
          // seller quitting from grace is below the fee by definition, which is
          // exactly who would have been misled by the unconditional promise.
          recovery={
            pptExit.balance >= pptExit.fee && pptExit.balance > 0
              ? t("exitPptRecovery")
              : pptExit.balance > 0
                ? t("exitPptRecoveryBelowFee", { fee: money(pptExit.fee) })
                : undefined
          }
          keepLabel={t("exitPptKeep")}
          confirmLabel={t("exitPptConfirm", { service: pptExit.serviceName })}
          busy={busyService === pptExit.serviceId}
          blocked={pptExit.balance < 0}
          error={pptExitError}
          onKeep={() => {
            setPptExitError(null);
            setPptExit(null);
          }}
          onConfirm={() => void handlePptExitConfirm()}
        />
      )}
    </div>
  );
}
