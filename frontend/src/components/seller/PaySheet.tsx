// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useState } from "react";

import Modal from "@/components/Modal";
import type { SellerPaymentDetails } from "@/lib/sellerPlan";
import styles from "./PaySheet.module.css";

export interface PaySheetProps {
  open: boolean;
  /** Purpose label, e.g. "Subscribe — Grocery · 3 months". */
  title: string;
  /** Fixed amount, or null when the seller enters it (amountEditable). */
  amount: number | null;
  amountEditable?: boolean;
  payment: SellerPaymentDetails;
  busy: boolean;
  /** Error from the last confirm attempt, shown in-sheet (role=alert). */
  error?: string | null;
  onConfirm: (opts: { amount: number; note: string | null }) => void;
  onClose: () => void;
}

function rupees(n: number): string {
  return `₹${n.toLocaleString("en-IN")}`;
}

export default function PaySheet({
  open,
  title,
  amount,
  amountEditable = false,
  payment,
  busy,
  error,
  onConfirm,
  onClose,
}: PaySheetProps) {
  const [amountInput, setAmountInput] = useState("");
  const [note, setNote] = useState("");
  const [showQr, setShowQr] = useState(false);

  if (!open) return null;

  const upiOn = payment.upi_enabled && Boolean(payment.upi_id || payment.qr_image_url);
  const bankOn =
    payment.bank_transfer_enabled && Boolean(payment.bank_account_number && payment.bank_ifsc);
  const anyMethod = upiOn || bankOn;

  const effectiveAmount = amountEditable ? Number(amountInput) : amount ?? 0;
  const amountValid = Number.isFinite(effectiveAmount) && effectiveAmount > 0;

  return (
    <Modal
      title="How to pay"
      size="sheet"
      onClose={onClose}
      footer={
        <div className={styles.footer}>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Close
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || !anyMethod || !amountValid}
            onClick={() => onConfirm({ amount: effectiveAmount, note: note.trim() || null })}
          >
            I&apos;ve paid
          </button>
        </div>
      }
    >
      <div className={styles.body}>
        {amountEditable ? (
          <label className={styles.amountLabel}>
            <span>Amount (₹)</span>
            <input
              type="number"
              inputMode="numeric"
              min={1}
              value={amountInput}
              onChange={(e) => setAmountInput(e.target.value)}
              className={styles.amountInput}
              aria-label="Payment amount"
            />
          </label>
        ) : (
          amount != null && <p className={styles.amount}>{rupees(amount)}</p>
        )}
        <p className={styles.purpose}>{title}</p>

        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}

        {!anyMethod ? (
          <p className={styles.empty} role="alert">
            Payment instructions are unavailable right now — please contact support.
          </p>
        ) : (
          <>
            <p className={styles.hint}>Pay using any method below, then tap “I’ve paid”.</p>

            {upiOn && (
              <div className={styles.method}>
                <p className={styles.methodName}>UPI</p>
                {payment.upi_id && <p className={styles.methodValue}>{payment.upi_id}</p>}
                {payment.qr_image_url && (
                  <button
                    type="button"
                    className="btn"
                    onClick={() => setShowQr((v) => !v)}
                  >
                    {showQr ? "Hide QR" : "Show QR"}
                  </button>
                )}
                {showQr && payment.qr_image_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    className={styles.qr}
                    src={payment.qr_image_url}
                    alt="Payment QR code"
                    referrerPolicy="no-referrer"
                  />
                )}
              </div>
            )}

            {bankOn && (
              <div className={styles.method}>
                <p className={styles.methodName}>Bank transfer</p>
                {payment.bank_account_name && (
                  <p className={styles.methodValue}>{payment.bank_account_name}</p>
                )}
                <p className={styles.methodValue}>A/c {payment.bank_account_number}</p>
                <p className={styles.methodValue}>IFSC {payment.bank_ifsc}</p>
              </div>
            )}

            {payment.gstin && (
              <p className={styles.gstin}>GSTIN {payment.gstin} — for your records</p>
            )}

            <label className={styles.noteLabel}>
              <span>Reference / UPI txn ID (optional)</span>
              <textarea
                className={styles.note}
                maxLength={200}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="e.g. UPI txn ID"
              />
            </label>
          </>
        )}
      </div>
    </Modal>
  );
}
