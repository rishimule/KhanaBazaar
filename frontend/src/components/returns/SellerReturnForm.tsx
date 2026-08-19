"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { apiErrorCode } from "@/lib/errors";
import {
  getSellerReturnEligibility,
  returnErrorKey,
  sellerCreateReturn,
} from "@/lib/returns";
import type {
  ReturnReasonCode,
  ReturnSettlementChoice,
  SellerReturnEligibility,
} from "@/types";
import styles from "./SellerReturnForm.module.css";

const REASONS: ReturnReasonCode[] = [
  "damaged",
  "wrong_item",
  "past_expiry",
  "quality_issue",
  "not_as_described",
  "other",
];

interface Props {
  orderId: number;
}

/**
 * Seller-initiated return. Posts the same body the customer wizard does, plus
 * the customer id. The customer still receives the confirmation code and must
 * accept the agreement, so consent never moves to the seller — this only opens
 * the request.
 */
export default function SellerReturnForm({ orderId }: Props) {
  const t = useTranslations("Seller.returns.initiate");
  // Operator-voiced errors live under Seller.returns.errors, matching the
  // seller return detail page.
  const te = useTranslations("Seller.returns");
  // Neutral shared copy (reason chips, lock notes, settlement labels) is
  // reused from the customer namespace; anything customer-voiced is not.
  const tr = useTranslations("Account.returns");
  const router = useRouter();
  const { token } = useAuth();

  const [eligibility, setEligibility] = useState<SellerReturnEligibility | null>(
    null
  );
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [reason, setReason] = useState<ReturnReasonCode>("damaged");
  const [note, setNote] = useState("");
  const [settlement, setSettlement] =
    useState<ReturnSettlementChoice>("store_credit");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await getSellerReturnEligibility(token, orderId);
        if (!cancelled) setEligibility(data);
      } catch (e) {
        // Never render a failed fetch as "nothing is returnable".
        if (!cancelled) setLoadError(apiErrorCode(e) ?? "unknown");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, orderId]);

  if (loadError) {
    return (
      <p role="alert" className={styles.error}>
        {t("loadFailed")}
      </p>
    );
  }
  if (!eligibility) return <p className={styles.muted}>{t("loading")}</p>;

  if (!eligibility.eligible) {
    return (
      <div className={styles.card}>
        <p className={styles.error}>
          {t(`ineligible.${eligibility.reason_code ?? "unknown"}`)}
        </p>
      </div>
    );
  }

  const allReturnable = eligibility.lines.filter((l) => l.returnable);
  const allSelected =
    allReturnable.length > 0 && selected.length === eligibility.lines.length;
  const feeReturned = allSelected && eligibility.full_order_available;
  const itemsTotal = eligibility.lines
    .filter((l) => selected.includes(l.order_item_id))
    .reduce((sum, l) => sum + l.line_total, 0);
  const previewTotal = itemsTotal + (feeReturned ? eligibility.delivery_fee : 0);

  const toggle = (id: number) =>
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );

  const submit = async () => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const created = await sellerCreateReturn(token, {
        order_id: orderId,
        customer_profile_id: eligibility.customer_profile_id,
        order_item_ids: selected,
        reason_code: reason,
        reason_note: note.trim() || null,
        settlement_choice: settlement,
      });
      router.push(`/seller/returns/${created.id}`);
    } catch (e) {
      setError(te(`errors.${returnErrorKey(apiErrorCode(e), "operator")}`));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={styles.form}>
      <p className={styles.consent}>
        {t("consentNote", { name: eligibility.customer_name })}
      </p>

      <section className={styles.card}>
        <h2 className={styles.heading}>{t("itemsTitle")}</h2>
        <p className={styles.muted}>{t("wholeLinesOnly")}</p>
        <ul className={styles.lines}>
          {eligibility.lines.map((line) => (
            <li key={line.order_item_id} className={styles.line}>
              <label className={line.returnable ? "" : styles.lockedLine}>
                <input
                  type="checkbox"
                  disabled={!line.returnable}
                  checked={selected.includes(line.order_item_id)}
                  onChange={() => toggle(line.order_item_id)}
                />
                <span className={styles.lineName}>
                  {line.product_name} × {line.quantity}
                </span>
                <span className={styles.lineTotal}>
                  ₹{line.line_total.toFixed(2)}
                </span>
              </label>
              {!line.returnable && (
                <p className={styles.lockNote}>
                  {tr(`lock.${line.lock_reason ?? "unknown"}`)}
                </p>
              )}
            </li>
          ))}
        </ul>
        {feeReturned && (
          <p className={styles.feeNote}>
            {tr("feeReturned", {
              amount: eligibility.delivery_fee.toFixed(2),
            })}
          </p>
        )}
      </section>

      <section className={styles.card}>
        <h2 className={styles.heading}>{t("reasonTitle")}</h2>
        <div className={styles.reasons}>
          {REASONS.map((code) => (
            <button
              key={code}
              type="button"
              className={`${styles.chip} ${reason === code ? styles.chipOn : ""}`}
              onClick={() => setReason(code)}
            >
              {tr(`reason.${code}`)}
            </button>
          ))}
        </div>
        <label className={styles.label} htmlFor="seller-return-note">
          {reason === "other" ? t("noteRequired") : t("noteOptional")}
        </label>
        <textarea
          id="seller-return-note"
          className={styles.textarea}
          value={note}
          maxLength={500}
          onChange={(e) => setNote(e.target.value)}
        />
      </section>

      <section className={styles.card}>
        <h2 className={styles.heading}>{t("settlementTitle")}</h2>
        <div className={styles.choices}>
          <button
            type="button"
            className={`${styles.choice} ${settlement === "store_credit" ? styles.choiceOn : ""}`}
            onClick={() => setSettlement("store_credit")}
          >
            <strong>{tr("settlementCredit")}</strong>
            <span>{t("settlementCreditHint")}</span>
          </button>
          <button
            type="button"
            className={`${styles.choice} ${settlement === "payment" ? styles.choiceOn : ""}`}
            onClick={() => setSettlement("payment")}
          >
            <strong>{tr("settlementPayment")}</strong>
            <span>{t("settlementPaymentHint")}</span>
          </button>
        </div>
        <p className={styles.muted}>{t("settlementCustomerNote")}</p>
      </section>

      <div className={styles.footer}>
        <p className={styles.total}>
          {t("previewTotal", { amount: previewTotal.toFixed(2) })}
        </p>
        <div className={styles.actions}>
          <button
            type="button"
            className="btn btn-primary"
            disabled={
              selected.length === 0 ||
              busy ||
              (reason === "other" && !note.trim())
            }
            onClick={submit}
          >
            {t("submit")}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => router.push(`/seller/orders/${orderId}`)}
          >
            {t("cancel")}
          </button>
        </div>
      </div>
      {error && (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      )}
    </div>
  );
}
