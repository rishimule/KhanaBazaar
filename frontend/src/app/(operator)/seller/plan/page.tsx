// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { useAuth } from "@/lib/AuthContext";
import PlanServiceCard from "@/components/seller/PlanServiceCard";
import {
  applyCreditPpt,
  cancelPlan,
  feeErrorCode,
  getMyPlan,
  markPaid,
  optIn,
  optInPpt,
  switchFromPpt,
  topUpPpt,
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
  amount_exceeds_credit: "That's more than your available wallet credit.",
  no_credit_available: "You have no wallet credit to apply.",
  balance_negative: "Settle the outstanding balance before switching plans.",
  bad_amount: "Enter a valid amount.",
};

function messageFor(code: string | null): string {
  return (code && ERROR_MESSAGES[code]) || "Something went wrong. Please try again.";
}

export default function SellerPlanPage() {
  const { token } = useAuth();
  const [data, setData] = useState<SellerPlanView | null>(null);
  const [fetching, setFetching] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyService, setBusyService] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setFetching(true);
    setLoadError(null);
    try {
      setData(await getMyPlan(token));
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

  const handleOptIn = (serviceId: number, duration: number) => {
    void run(serviceId, () => optIn(serviceId, duration, token));
  };
  const handleMarkPaid = (serviceId: number, note: string | null) => {
    void run(serviceId, () => markPaid(serviceId, note, token));
  };
  const handleCancel = (serviceId: number) => {
    if (
      !window.confirm(
        "Cancel this subscription? It stays active until the end of the paid term, then stops renewing.",
      )
    ) {
      return;
    }
    void run(serviceId, () => cancelPlan(serviceId, token));
  };

  const handleOptInPpt = (serviceId: number, deposit: number, useCredit: boolean) => {
    void run(serviceId, () => optInPpt(serviceId, deposit, useCredit, token));
  };
  const handleTopUp = (serviceId: number) => {
    const raw = window.prompt("Top-up amount (₹) — pay this offline via the QR/bank details, then an admin confirms it:");
    if (raw == null) return;
    const amount = Number(raw);
    if (!Number.isFinite(amount) || amount <= 0) {
      setActionError("Enter a valid amount.");
      return;
    }
    void run(serviceId, () => topUpPpt(serviceId, amount, token));
  };
  const handleApplyCredit = (serviceId: number) => {
    const raw = window.prompt("Amount of wallet credit to move into this balance (₹):");
    if (raw == null) return;
    const amount = Number(raw);
    if (!Number.isFinite(amount) || amount <= 0) {
      setActionError("Enter a valid amount.");
      return;
    }
    void run(serviceId, () => applyCreditPpt(serviceId, amount, token));
  };
  const handleSwitchPpt = (serviceId: number) => {
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
          <p className={styles.subtitle}>
            Manage your store&apos;s platform-fee plan for each service.
          </p>
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
              payment={data.payment_details}
              busy={busyService === s.service_id}
              feeCredit={data.fee_credit_balance}
              onOptIn={handleOptIn}
              onMarkPaid={handleMarkPaid}
              onCancel={handleCancel}
              onOptInPpt={handleOptInPpt}
              onTopUp={handleTopUp}
              onApplyCredit={handleApplyCredit}
              onSwitchPpt={handleSwitchPpt}
            />
          ))}
        </div>
      )}
    </div>
  );
}
