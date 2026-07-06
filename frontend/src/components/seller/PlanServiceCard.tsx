// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useState } from "react";

import type {
  SellerPaymentDetails,
  SellerPlanServiceView,
} from "@/lib/sellerPlan";
import styles from "./PlanServiceCard.module.css";

interface Props {
  service: SellerPlanServiceView;
  payment: SellerPaymentDetails;
  busy: boolean;
  onOptIn: (serviceId: number, durationMonths: number) => void;
  onMarkPaid: (serviceId: number, sellerNote: string | null) => void;
  onCancel: (serviceId: number) => void;
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

function fmtDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function daysLeft(iso: string): number {
  return Math.ceil((new Date(`${iso}T00:00:00`).getTime() - Date.now()) / 86_400_000);
}

export default function PlanServiceCard({
  service,
  payment,
  busy,
  onOptIn,
  onMarkPaid,
  onCancel,
}: Props) {
  const activePlans = service.subscription_plans.filter((p) => p.is_active);
  const [duration, setDuration] = useState<number>(
    () => activePlans[0]?.duration_months ?? 0,
  );
  const [showNote, setShowNote] = useState(false);
  const [note, setNote] = useState("");

  const isPaidSub = service.model === "subscription";
  const isLive = service.status === "active" || service.status === "grace";
  const pill = service.payment_pending
    ? { label: "Payment under review", kind: "warning" }
    : STATUS_PILL[service.status] ?? { label: service.status, kind: "neutral" };

  const showOptIn =
    service.subscription_enabled &&
    activePlans.length > 0 &&
    !service.payment_pending &&
    !service.cancel_requested;
  const showCancel =
    isPaidSub && service.status === "active" && !service.cancel_requested && !service.payment_pending;
  const noPaidPlans =
    !service.payment_pending &&
    (!service.subscription_enabled || activePlans.length === 0) &&
    service.model === "freebie";

  // Validity line
  let validity: string | null = null;
  if (service.cancel_requested && service.valid_until) {
    validity = `Cancellation scheduled — access until ${fmtDate(service.valid_until)}.`;
  } else if (service.valid_until) {
    const d = daysLeft(service.valid_until);
    const left = d > 0 ? ` · ${d} day${d === 1 ? "" : "s"} left` : " · expired";
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

      {noPaidPlans && (
        <p className={styles.muted}>No paid plans are available for this service yet.</p>
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
