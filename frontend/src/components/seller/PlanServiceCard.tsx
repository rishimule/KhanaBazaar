// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useState } from "react";

import type {
  FeeInvoice,
  SellerPaymentDetails,
  SellerPlanServiceView,
} from "@/lib/sellerPlan";
import styles from "./PlanServiceCard.module.css";

interface Props {
  service: SellerPlanServiceView;
  payment: SellerPaymentDetails;
  busy: boolean;
  feeCredit: number;
  /** Order Value % invoices for this service (empty/undefined otherwise). */
  invoices?: FeeInvoice[];
  onOptIn: (serviceId: number, durationMonths: number) => void;
  onMarkPaid: (serviceId: number, sellerNote: string | null) => void;
  onCancel: (serviceId: number) => void;
  onOptInPpt: (serviceId: number, deposit: number, useCredit: boolean) => void;
  onTopUp: (serviceId: number) => void;
  onApplyCredit: (serviceId: number) => void;
  onSwitchPpt: (serviceId: number) => void;
  onOptInOrderValue: (serviceId: number, deposit: number) => void;
  onPayInvoice: (serviceId: number, invoiceId: number) => void;
}

const MODEL_LABEL: Record<string, string> = {
  freebie: "Free trial",
  subscription: "Subscription",
  order_value_percent: "Order-value %",
  pay_per_transaction: "Pay per order",
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

// valid_until is a date string per the contract; slice defensively so a full
// ISO timestamp (if ever returned) still parses instead of yielding NaN.
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
  payment,
  busy,
  feeCredit,
  invoices,
  onOptIn,
  onMarkPaid,
  onCancel,
  onOptInPpt,
  onTopUp,
  onApplyCredit,
  onSwitchPpt,
  onOptInOrderValue,
  onPayInvoice,
}: Props) {
  const activePlans = service.subscription_plans.filter((p) => p.is_active);
  const [duration, setDuration] = useState<number>(
    () => activePlans[0]?.duration_months ?? 0,
  );
  const [showNote, setShowNote] = useState(false);
  const [note, setNote] = useState("");
  const [pptDeposit, setPptDeposit] = useState<string>("");
  const [pptUseCredit, setPptUseCredit] = useState(false);
  const [ovDeposit, setOvDeposit] = useState<string>("");

  const isPaidSub = service.model === "subscription";
  const isPpt = service.model === "pay_per_transaction";
  const isOrderValue = service.model === "order_value_percent";
  const isLive = service.status === "active" || service.status === "grace";
  const pill = service.payment_pending
    ? { label: "Payment under review", kind: "warning" }
    : STATUS_PILL[service.status] ?? { label: service.status, kind: "neutral" };

  const showOptIn =
    service.subscription_enabled &&
    activePlans.length > 0 &&
    !service.payment_pending &&
    !service.cancel_requested;
  // A non-PPT service the admin has enabled for pay-per-order → offer opt-in.
  const showPptOptIn =
    service.pay_per_txn_enabled && !isPpt && !service.payment_pending;
  // A service the admin has enabled for Order Value % → offer opt-in.
  const showOvOptIn =
    service.order_value_enabled && !isOrderValue && !isPpt && !service.payment_pending;
  const showCancel =
    isPaidSub && service.status === "active" && !service.cancel_requested && !service.payment_pending;
  // Nothing to act on (no opt-in panel, no pending payment, no cancel) — show
  // an explanatory line instead of a bare card. Covers freebie-with-no-plans
  // and a subscription whose plans were all deactivated.
  const noActionable =
    !showOptIn && !showCancel && !isPpt && !isOrderValue && !showPptOptIn && !showOvOptIn &&
    !service.payment_pending && !service.cancel_requested;

  // Order Value % (postpaid) derived values.
  const ovInvoices = invoices ?? [];
  const ovDeposited = service.security_deposit_amount ?? 0;
  const ovOutstanding = service.outstanding_balance ?? 0;
  const ovHasOverdue = ovInvoices.some((i) => i.status === "overdue");
  const ovMinDeposit = service.order_value_min_deposit || 0;

  // Pay-Per-Transaction balance meter.
  const fee = service.pay_per_txn_fee || 0;
  const balance = service.balance ?? 0;
  const lowThr = service.low_balance_threshold ?? 0;
  const meterTarget = Math.max(lowThr * 2, fee * 10, 1);
  const meterPct = Math.max(4, Math.min(100, (balance / meterTarget) * 100));
  const belowFee = isPpt && balance < fee;
  const lowBalance = isPpt && !belowFee && lowThr > 0 && balance < lowThr;
  const meterColor = belowFee
    ? "var(--color-status-warning, #FF5026)"
    : lowBalance
      ? "var(--accent-turmeric, #F18A1F)"
      : "var(--brand-flag-green, #138808)";

  // Validity line
  let validity: string | null = null;
  if (service.cancel_requested && service.valid_until) {
    validity = `Cancellation scheduled — access until ${fmtDate(service.valid_until)}.`;
  } else if (service.valid_until) {
    const d = daysLeft(service.valid_until);
    const left = Number.isFinite(d)
      ? d > 0
        ? ` · ${d} day${d === 1 ? "" : "s"} left`
        : " · expired"
      : "";
    validity =
      service.model === "freebie"
        ? `Trial ends ${fmtDate(service.valid_until)}${left}`
        : `Valid until ${fmtDate(service.valid_until)}${left}`;
  }

  const payRows: [string, string | null][] = [
    ["Account name", payment.bank_account_name],
    ["Account number", payment.bank_account_number],
    ["IFSC", payment.bank_ifsc],
    ["UPI ID", payment.upi_id],
    ["GSTIN", payment.gstin],
  ];

  return (
    <section className={styles.card}>
      <header className={styles.header}>
        <h2 className={styles.title}>{service.service_name}</h2>
        <span className={`badge badge--${pill.kind}`}>{pill.label}</span>
      </header>

      <p className={styles.model}>{MODEL_LABEL[service.model] ?? service.model}</p>
      {validity && <p className={styles.validity}>{validity}</p>}

      {noActionable && (
        <p className={styles.muted}>No paid plans are available for this service right now.</p>
      )}

      {isPpt && (
        <div className={styles.payBox}>
          <p className={styles.sectionTitle}>Prepaid balance</p>
          <p className={styles.amount}>{rupees(balance)}</p>
          <div
            style={{
              height: 8,
              borderRadius: 100,
              background: "var(--surface-tint, #EEF2FB)",
              overflow: "hidden",
              margin: "6px 0",
            }}
          >
            <div style={{ height: "100%", width: `${meterPct}%`, borderRadius: 100, background: meterColor }} />
          </div>
          <p className={styles.muted}>
            {rupees(fee)} per order
            {belowFee ? " · low balance" : lowBalance ? " · running low" : ""}
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
            <button
              type="button"
              className="btn"
              disabled={busy || feeCredit <= 0}
              onClick={() => onApplyCredit(service.service_id)}
            >
              Apply credit
            </button>
            <button type="button" className={styles.cancelBtn} disabled={busy} onClick={() => onSwitchPpt(service.service_id)}>
              Switch plan
            </button>
          </div>
          <p className={styles.muted}>Store wallet credit available: {rupees(feeCredit)}</p>
        </div>
      )}

      {isOrderValue && (
        <div className={styles.payBox}>
          <p className={styles.sectionTitle}>{service.order_value_percent}% of monthly sales</p>
          <p className={styles.muted}>
            Security deposit held as collateral · invoiced on day{" "}
            {service.order_value_billing_day} for the previous month · payable within{" "}
            {service.order_value_payment_days} days · incl. GST.
          </p>
          {(ovHasOverdue || service.status === "suspended") && (
            <p
              className={styles.muted}
              style={{
                background: "var(--color-status-warning-tint, #FEEFDB)",
                color: "var(--color-status-pending-text, #92400E)",
                borderRadius: 10,
                padding: "10px 12px",
              }}
            >
              {service.status === "suspended"
                ? "Service suspended for non-payment. Clear your outstanding invoice to reactivate."
                : "You have an overdue invoice. Pay it to avoid suspension."}
            </p>
          )}
          <div style={{ display: "flex", gap: 12, margin: "4px 0" }}>
            <div className={styles.section} style={{ flex: 1, margin: 0, padding: 12 }}>
              <p className={styles.muted} style={{ margin: 0 }}>Security deposit held</p>
              <p className={styles.amount} style={{ margin: 0 }}>{rupees(ovDeposited)}</p>
            </div>
            <div className={styles.section} style={{ flex: 1, margin: 0, padding: 12 }}>
              <p className={styles.muted} style={{ margin: 0 }}>Outstanding</p>
              <p className={styles.amount} style={{ margin: 0 }}>{rupees(ovOutstanding)}</p>
            </div>
          </div>
          {ovInvoices.length > 0 && (
            <>
              <p className={styles.sectionTitle}>Invoices</p>
              <ul style={{ listStyle: "none", margin: 0, padding: 0, border: "1px solid var(--color-border-divider, #EAEAEA)", borderRadius: 10, overflow: "hidden" }}>
                {ovInvoices.map((inv, idx) => {
                  const kind =
                    inv.status === "paid" ? "member"
                      : inv.status === "overdue" ? "sale"
                        : inv.status === "pending" ? "warning" : "neutral";
                  const payable = inv.status === "pending" || inv.status === "overdue";
                  return (
                    <li
                      key={inv.id}
                      style={{
                        display: "flex", alignItems: "center", gap: 10, padding: "10px 12px",
                        borderTop: idx === 0 ? "none" : "1px solid var(--color-border-divider, #EAEAEA)",
                      }}
                    >
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div>{fmtMonth(inv.period_start)}</div>
                        <div className={styles.muted} style={{ fontSize: 12 }}>
                          Sales {rupees(inv.sales_total)} · {inv.fee_percent_snapshot}%
                        </div>
                      </div>
                      <span>{rupees(inv.amount_due)}</span>
                      <span className={`badge badge--${kind}`}>{inv.status}</span>
                      {payable && (
                        <button
                          type="button"
                          className="btn btn-primary"
                          disabled={busy || service.payment_pending}
                          onClick={() => onPayInvoice(service.service_id, inv.id)}
                        >
                          Pay
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </div>
      )}

      {showOvOptIn && (
        <div className={styles.section}>
          <p className={styles.sectionTitle}>Start Order Value %</p>
          <p className={styles.muted}>
            Postpaid: {service.order_value_percent || 0}% of each month’s completed sales,
            invoiced on day {service.order_value_billing_day}. Pay a refundable security
            deposit of at least {rupees(ovMinDeposit)} to activate.
          </p>
          <input
            type="number"
            inputMode="numeric"
            min={ovMinDeposit}
            className={styles.note}
            style={{ maxWidth: 200 }}
            value={ovDeposit}
            onChange={(e) => setOvDeposit(e.target.value)}
            placeholder={`Deposit (min ${rupees(ovMinDeposit)})`}
            aria-label="Security deposit amount"
          />
          <div className={styles.actions}>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || Number(ovDeposit) < ovMinDeposit || Number(ovDeposit) <= 0}
              onClick={() => onOptInOrderValue(service.service_id, Number(ovDeposit))}
            >
              Pay deposit &amp; start
            </button>
          </div>
        </div>
      )}

      {showPptOptIn && (
        <div className={styles.section}>
          <p className={styles.sectionTitle}>Start pay-per-order</p>
          <p className={styles.muted}>
            Prepay a deposit; {rupees(service.pay_per_txn_fee)} is charged per order. Minimum
            deposit {rupees(service.pay_per_txn_min_deposit)}.
          </p>
          <input
            type="number"
            inputMode="numeric"
            min={service.pay_per_txn_min_deposit}
            className={styles.note}
            style={{ maxWidth: 200 }}
            value={pptDeposit}
            onChange={(e) => setPptDeposit(e.target.value)}
            placeholder={`Deposit (min ${rupees(service.pay_per_txn_min_deposit)})`}
            aria-label="Deposit amount"
          />
          {feeCredit > 0 && (
            <label className={styles.muted} style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={pptUseCredit}
                onChange={(e) => setPptUseCredit(e.target.checked)}
              />
              Pay the deposit from my wallet credit ({rupees(feeCredit)})
            </label>
          )}
          <div className={styles.actions}>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || Number(pptDeposit) < service.pay_per_txn_min_deposit || Number(pptDeposit) <= 0}
              onClick={() => onOptInPpt(service.service_id, Number(pptDeposit), pptUseCredit)}
            >
              Start pay-per-order
            </button>
          </div>
        </div>
      )}

      {service.payment_pending && (
        <div className={styles.payBox}>
          <p className={styles.payHead}>Payment under review</p>
          {service.amount_due != null && (
            <p className={styles.amount}>Amount due: {rupees(service.amount_due)}</p>
          )}
          <p className={styles.payIntro}>
            Pay offline using the details below, then tap “I’ve paid”. We activate
            your plan once the team confirms receipt.
          </p>
          <dl className={styles.payRows}>
            {payRows.map(([label, value]) =>
              value ? (
                <div className={styles.payRow} key={label}>
                  <dt className={styles.payLabel}>{label}</dt>
                  <dd className={styles.payValue}>{value}</dd>
                </div>
              ) : null,
            )}
          </dl>
          {payment.qr_image_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              className={styles.qr}
              src={payment.qr_image_url}
              alt="Payment QR code"
              referrerPolicy="no-referrer"
            />
          )}
          {showNote ? (
            <div className={styles.noteWrap}>
              <label className={styles.noteLabel} htmlFor={`note-${service.service_id}`}>
                UPI reference (optional)
              </label>
              <textarea
                id={`note-${service.service_id}`}
                className={styles.note}
                maxLength={200}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="e.g. UPI txn ID"
              />
              <div className={styles.actions}>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={() => onMarkPaid(service.service_id, note.trim() || null)}
                >
                  Confirm “I’ve paid”
                </button>
              </div>
            </div>
          ) : (
            <div className={styles.actions}>
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={() => setShowNote(true)}
              >
                I’ve paid
              </button>
            </div>
          )}
        </div>
      )}

      {showOptIn && (
        <div className={styles.section}>
          <p className={styles.sectionTitle}>
            {isPaidSub && isLive ? "Renew or change plan" : "Upgrade to a paid plan"}
          </p>
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
              disabled={busy || duration === 0}
              onClick={() => onOptIn(service.service_id, duration)}
            >
              {isPaidSub && isLive ? "Renew" : "Subscribe"}
            </button>
          </div>
        </div>
      )}

      {showCancel && (
        <button
          type="button"
          className={styles.cancelBtn}
          disabled={busy}
          onClick={() => onCancel(service.service_id)}
        >
          Cancel subscription
        </button>
      )}
    </section>
  );
}
