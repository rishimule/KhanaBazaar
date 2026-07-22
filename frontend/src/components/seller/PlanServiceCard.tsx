// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useState } from "react";

import type { FeeInvoice, SellerPlanServiceView } from "@/lib/sellerPlan";
import styles from "./PlanServiceCard.module.css";

interface Props {
  service: SellerPlanServiceView;
  busy: boolean;
  feeCredit: number;
  /** Order Value % invoices for this service (empty/undefined otherwise). */
  invoices?: FeeInvoice[];
  /** Openers — these raise the page-level pay sheet. */
  onSubscribe: (serviceId: number, durationMonths: number, price: number) => void;
  onStartOrderValue: (serviceId: number, deposit: number) => void;
  onStartPpt: (serviceId: number, deposit: number) => void;
  onTopUp: (serviceId: number) => void;
  onPayInvoice: (serviceId: number, invoiceId: number, amount: number) => void;
  /** Direct actions — no offline payment. */
  onCancel: (serviceId: number) => void;
  onStartPptWithCredit: (serviceId: number, deposit: number) => void;
  onApplyCredit: (serviceId: number, amount: number) => void;
  onStopPpt: (serviceId: number) => void;
}

type ModelKey = "freebie" | "subscription" | "order_value_percent" | "pay_per_transaction";

const MODEL_ORDER: ModelKey[] = [
  "freebie",
  "subscription",
  "order_value_percent",
  "pay_per_transaction",
];

const MODEL_LABEL: Record<string, string> = {
  freebie: "Free trial",
  subscription: "Subscription",
  order_value_percent: "Order-value %",
  pay_per_transaction: "Pay-per-order",
};

const STATUS_PILL: Record<string, { label: string; kind: string }> = {
  trial: { label: "Free trial", kind: "neutral" },
  active: { label: "Active", kind: "member" },
  grace: { label: "Grace period", kind: "warning" },
  suspended: { label: "Suspended", kind: "sale" },
  pending_activation: { label: "Pending", kind: "warning" },
};

function rupees(n: number): string {
  return `₹${n.toLocaleString("en-IN")}`;
}
function parseDate(iso: string): Date {
  return new Date(`${iso.slice(0, 10)}T00:00:00`);
}
function fmtDate(iso: string): string {
  const d = parseDate(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}
function daysLeft(iso: string): number {
  return Math.ceil((parseDate(iso).getTime() - Date.now()) / 86_400_000);
}
function fmtMonth(iso: string): string {
  const d = parseDate(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-IN", { month: "short", year: "numeric" });
}

export default function PlanServiceCard({
  service,
  busy,
  feeCredit,
  invoices,
  onSubscribe,
  onStartOrderValue,
  onStartPpt,
  onTopUp,
  onPayInvoice,
  onCancel,
  onStartPptWithCredit,
  onApplyCredit,
  onStopPpt,
}: Props) {
  const activePlans = service.subscription_plans.filter((p) => p.is_active);
  const [selected, setSelected] = useState<string>(service.model);
  const [duration, setDuration] = useState<number>(() => activePlans[0]?.duration_months ?? 0);
  const [ovDeposit, setOvDeposit] = useState("");
  const [pptDeposit, setPptDeposit] = useState("");
  const [creditAmt, setCreditAmt] = useState("");

  const pending = service.payment_pending;
  const isLive = service.status === "active" || service.status === "grace";

  // Which model tabs to show: the current model always, plus any the admin
  // enabled as an opt-in target. Freebie is never a switch target.
  const segments = MODEL_ORDER.filter((m) => {
    if (m === service.model) return true;
    if (m === "subscription") return service.subscription_enabled && activePlans.length > 0;
    if (m === "order_value_percent") return service.order_value_enabled;
    if (m === "pay_per_transaction") return service.pay_per_txn_enabled;
    return false;
  });

  const pill = pending
    ? { label: "Payment under review", kind: "warning" }
    : STATUS_PILL[service.status] ?? { label: service.status, kind: "neutral" };

  const isActiveModel = (m: string) => m === service.model;

  // ── Validity line (for the active model) ─────────────────────────────
  let validity: string | null = null;
  if (service.cancel_requested && service.valid_until) {
    validity = `Cancellation scheduled — access until ${fmtDate(service.valid_until)}.`;
  } else if (service.valid_until) {
    const d = daysLeft(service.valid_until);
    const left = Number.isFinite(d) ? (d > 0 ? ` · ${d} day${d === 1 ? "" : "s"} left` : " · expired") : "";
    validity =
      service.model === "freebie"
        ? `Trial ends ${fmtDate(service.valid_until)}${left}`
        : `Valid until ${fmtDate(service.valid_until)}${left}`;
  }

  // ── Subscription tab ─────────────────────────────────────────────────
  function renderSubscription() {
    const active = isActiveModel("subscription");
    if (activePlans.length === 0) {
      return <p className={styles.muted}>No subscription plans are available for this service right now.</p>;
    }
    const selectedPlan = activePlans.find((p) => p.duration_months === duration);
    return (
      <div className={styles.section}>
        <p className={styles.sectionTitle}>{active && isLive ? "Renew or change plan" : "Subscribe"}</p>
        {active && validity && <p className={styles.validity}>{validity}</p>}
        <div className={styles.options} role="radiogroup" aria-label="Subscription duration">
          {activePlans.map((p) => (
            <label
              key={p.duration_months}
              className={`${styles.option} ${duration === p.duration_months ? styles.optionSelected : ""}`}
            >
              <input
                type="radio"
                name={`plan-${service.service_id}`}
                checked={duration === p.duration_months}
                onChange={() => setDuration(p.duration_months)}
              />
              <span className={styles.optionMonths}>{p.duration_months} months</span>
              <span className={styles.optionPrice}>{rupees(p.price)}</span>
            </label>
          ))}
        </div>
        <div className={styles.actions}>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || pending || duration === 0 || service.cancel_requested}
            onClick={() => onSubscribe(service.service_id, duration, selectedPlan?.price ?? 0)}
          >
            {active && isLive ? "Renew" : "Subscribe"}
          </button>
        </div>
        {active && service.status === "active" && !service.cancel_requested && !pending && (
          <button type="button" className={styles.cancelBtn} disabled={busy} onClick={() => onCancel(service.service_id)}>
            Cancel subscription
          </button>
        )}
      </div>
    );
  }

  // ── Order Value % tab ────────────────────────────────────────────────
  function renderOrderValue() {
    const active = isActiveModel("order_value_percent");
    const ovInvoices = invoices ?? [];
    const ovDeposited = service.security_deposit_amount ?? 0;
    const ovOutstanding = service.outstanding_balance ?? 0;
    const ovHasOverdue = ovInvoices.some((i) => i.status === "overdue");
    const ovMinDeposit = service.order_value_min_deposit || 0;

    if (!active) {
      return (
        <div className={styles.section}>
          <p className={styles.sectionTitle}>Start Order-value %</p>
          <p className={styles.muted}>
            Postpaid: {service.order_value_percent || 0}% of each month’s completed sales, invoiced on day{" "}
            {service.order_value_billing_day}. Pay a refundable security deposit of at least {rupees(ovMinDeposit)} to
            activate.
          </p>
          <input
            type="number"
            inputMode="numeric"
            min={ovMinDeposit}
            className={styles.inlineInput}
            value={ovDeposit}
            onChange={(e) => setOvDeposit(e.target.value)}
            placeholder={`Deposit (min ${rupees(ovMinDeposit)})`}
            aria-label="Security deposit amount"
          />
          <div className={styles.actions}>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || pending || Number(ovDeposit) < ovMinDeposit || Number(ovDeposit) <= 0}
              onClick={() => onStartOrderValue(service.service_id, Number(ovDeposit))}
            >
              Pay deposit &amp; start
            </button>
          </div>
        </div>
      );
    }

    return (
      <div className={styles.payBox}>
        <p className={styles.sectionTitle}>{service.order_value_percent}% of monthly sales</p>
        {validity && <p className={styles.validity}>{validity}</p>}
        <p className={styles.muted}>
          Security deposit held as collateral · invoiced on day {service.order_value_billing_day} for the previous month
          · payable within {service.order_value_payment_days} days · incl. GST.
        </p>
        {(ovHasOverdue || service.status === "suspended") && (
          <p className={styles.warnBox}>
            {service.status === "suspended"
              ? "Service suspended for non-payment. Clear your outstanding invoice to reactivate."
              : "You have an overdue invoice. Pay it to avoid suspension."}
          </p>
        )}
        <div className={styles.statRow}>
          <div className={styles.stat}>
            <p className={styles.muted} style={{ margin: 0 }}>Security deposit held</p>
            <p className={styles.amount} style={{ margin: 0 }}>{rupees(ovDeposited)}</p>
          </div>
          <div className={styles.stat}>
            <p className={styles.muted} style={{ margin: 0 }}>Outstanding</p>
            <p className={styles.amount} style={{ margin: 0 }}>{rupees(ovOutstanding)}</p>
          </div>
        </div>
        {ovInvoices.length > 0 && (
          <>
            <p className={styles.sectionTitle} style={{ marginTop: 12 }}>Invoices</p>
            <ul className={styles.invoiceList}>
              {ovInvoices.map((inv) => {
                const kind =
                  inv.status === "paid" ? "member"
                    : inv.status === "overdue" ? "sale"
                      : inv.status === "pending" ? "warning" : "neutral";
                const payable = inv.status === "pending" || inv.status === "overdue";
                return (
                  <li key={inv.id} className={styles.invoiceRow}>
                    <div className={styles.invoiceMeta}>
                      <div>{fmtMonth(inv.period_start)}</div>
                      <div className={styles.muted} style={{ fontSize: 12, marginTop: 0 }}>
                        Sales {rupees(inv.sales_total)} · {inv.fee_percent_snapshot}%
                      </div>
                    </div>
                    <span>{rupees(inv.amount_due)}</span>
                    <span className={`badge badge--${kind}`}>{inv.status}</span>
                    {inv.payment_pending ? (
                      <span className="badge badge--warning">Under review</span>
                    ) : (
                      payable && (
                        <button
                          type="button"
                          className="btn btn-primary"
                          disabled={busy}
                          onClick={() => onPayInvoice(service.service_id, inv.id, inv.amount_due)}
                        >
                          Pay
                        </button>
                      )
                    )}
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>
    );
  }

  // ── Pay-per-order tab ────────────────────────────────────────────────
  function renderPpt() {
    const active = isActiveModel("pay_per_transaction");
    const fee = service.pay_per_txn_fee || 0;

    if (!active) {
      const dep = Number(pptDeposit);
      const min = service.pay_per_txn_min_deposit || 0;
      const canCredit = feeCredit >= dep && dep >= min && dep > 0;
      return (
        <div className={styles.section}>
          <p className={styles.sectionTitle}>Start pay-per-order</p>
          <p className={styles.muted}>
            Prepay a deposit; {rupees(fee)} is charged per order. Minimum deposit {rupees(min)}.
          </p>
          <input
            type="number"
            inputMode="numeric"
            min={min}
            className={styles.inlineInput}
            value={pptDeposit}
            onChange={(e) => setPptDeposit(e.target.value)}
            placeholder={`Deposit (min ${rupees(min)})`}
            aria-label="Deposit amount"
          />
          <div className={styles.actions}>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || pending || dep < min || dep <= 0}
              onClick={() => onStartPpt(service.service_id, dep)}
            >
              Start pay-per-order
            </button>
            {feeCredit > 0 && (
              <button
                type="button"
                className="btn"
                disabled={busy || pending || !canCredit}
                onClick={() => onStartPptWithCredit(service.service_id, dep)}
              >
                Pay from wallet credit ({rupees(feeCredit)})
              </button>
            )}
          </div>
        </div>
      );
    }

    const balance = service.balance ?? 0;
    const lowThr = service.low_balance_threshold ?? 0;
    const meterTarget = Math.max(lowThr * 2, fee * 10, 1);
    const meterPct = Math.max(4, Math.min(100, (balance / meterTarget) * 100));
    const belowFee = balance < fee;
    const lowBalance = !belowFee && lowThr > 0 && balance < lowThr;
    const meterColor = belowFee
      ? "var(--color-status-warning, #FF5026)"
      : lowBalance
        ? "var(--accent-turmeric, #F18A1F)"
        : "var(--brand-flag-green, #138808)";

    return (
      <div className={styles.payBox}>
        <p className={styles.sectionTitle}>Prepaid balance</p>
        <p className={styles.amount}>{rupees(balance)}</p>
        <div className={styles.meterTrack}>
          <div className={styles.meterFill} style={{ width: `${meterPct}%`, background: meterColor }} />
        </div>
        <p className={styles.muted}>
          {rupees(fee)} per order{belowFee ? " · low balance" : lowBalance ? " · running low" : ""}
        </p>
        {(service.status === "grace" || service.status === "suspended") && (
          <p className={styles.muted}>
            {service.status === "grace"
              ? "Balance is below one order fee. Top up within the grace period, or the service is suspended."
              : "Service suspended — top up to reactivate and receive new orders."}
          </p>
        )}
        <div className={styles.actions}>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={() => onTopUp(service.service_id)}>
            Top up
          </button>
          <button type="button" className={styles.cancelBtn} disabled={busy} onClick={() => onStopPpt(service.service_id)}>
            Stop pay-per-order
          </button>
        </div>
        {feeCredit > 0 && (
          <div className={styles.creditRow}>
            <input
              type="number"
              inputMode="numeric"
              min={1}
              className={styles.inlineInput}
              value={creditAmt}
              onChange={(e) => setCreditAmt(e.target.value)}
              placeholder="Amount"
              aria-label="Wallet credit to apply"
            />
            <button
              type="button"
              className="btn"
              disabled={busy || Number(creditAmt) <= 0 || Number(creditAmt) > feeCredit}
              onClick={() => onApplyCredit(service.service_id, Number(creditAmt))}
            >
              Apply credit
            </button>
            <span className={styles.muted} style={{ margin: 0 }}>Wallet: {rupees(feeCredit)}</span>
          </div>
        )}
      </div>
    );
  }

  // ── Freebie tab (only ever the active model) ─────────────────────────
  function renderFreebie() {
    const hasPaidOption = segments.some((m) => m !== "freebie");
    return (
      <div className={styles.section}>
        {validity && <p className={styles.validity}>{validity}</p>}
        <p className={styles.muted}>
          {hasPaidOption
            ? "You’re on a free trial. Choose a paid plan above to continue after it ends."
            : "You’re on a free trial. No paid plans are available for this service right now."}
        </p>
      </div>
    );
  }

  return (
    <section className={styles.card}>
      <header className={styles.header}>
        <h2 className={styles.title}>{service.service_name}</h2>
        <span className={`badge badge--${pill.kind}`}>{pill.label}</span>
      </header>

      {segments.length > 1 && (
        <div className={styles.tabs} role="tablist" aria-label="Fee plan">
          {segments.map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={selected === m}
              className={`${styles.tab} ${selected === m ? styles.tabActive : ""}`}
              onClick={() => setSelected(m)}
            >
              {MODEL_LABEL[m]}
              {isActiveModel(m) && <span className={styles.dot} aria-hidden />}
            </button>
          ))}
        </div>
      )}

      {pending && (
        <p className={styles.muted}>
          Payment under review — we’ll activate your plan once the team confirms receipt.
        </p>
      )}

      {selected === "subscription" && renderSubscription()}
      {selected === "order_value_percent" && renderOrderValue()}
      {selected === "pay_per_transaction" && renderPpt()}
      {selected === "freebie" && renderFreebie()}

      <p className={styles.caption}>
        Only one plan is active per service at a time. Switching replaces the current plan.
      </p>
    </section>
  );
}
