"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { apiErrorCode } from "@/lib/errors";
import {
  confirmReturn,
  createReturn,
  getReturnEligibility,
  resendReturnOtp,
} from "@/lib/returns";
import type {
  ReturnEligibility,
  ReturnReasonCode,
  ReturnRequest,
  ReturnSettlementChoice,
} from "@/types";
import styles from "./ReturnWizard.module.css";

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
  /** Rendered above the agreement so the customer reads the real published
   *  terms, not copy baked into this component. */
  agreementBody: string | null;
}

type Step = 1 | 2 | 3 | 4;

export default function ReturnWizard({ orderId, agreementBody }: Props) {
  const t = useTranslations("Account.returns");
  const router = useRouter();
  const { token } = useAuth();

  const [eligibility, setEligibility] = useState<ReturnEligibility | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [step, setStep] = useState<Step>(1);
  const [selected, setSelected] = useState<number[]>([]);
  const [reason, setReason] = useState<ReturnReasonCode>("damaged");
  const [note, setNote] = useState("");
  const [settlement, setSettlement] =
    useState<ReturnSettlementChoice>("store_credit");
  const [accepted, setAccepted] = useState(false);
  const [otp, setOtp] = useState("");
  const [created, setCreated] = useState<ReturnRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await getReturnEligibility(token, orderId);
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

  const returnable = eligibility.lines.filter((l) => l.returnable);
  const allSelected =
    returnable.length > 0 && selected.length === eligibility.lines.length;
  const feeReturned = allSelected && eligibility.full_order_available;
  const itemsTotal = eligibility.lines
    .filter((l) => selected.includes(l.order_item_id))
    .reduce((sum, l) => sum + l.line_total, 0);
  const previewTotal = itemsTotal + (feeReturned ? eligibility.delivery_fee : 0);

  const toggle = (id: number) =>
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );

  const selectAll = () =>
    setSelected(
      allSelected ? [] : eligibility.lines.filter((l) => l.returnable).map((l) => l.order_item_id)
    );

  const submitDraft = async () => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const req = await createReturn(token, {
        order_id: orderId,
        order_item_ids: selected,
        reason_code: reason,
        reason_note: note.trim() || null,
        settlement_choice: settlement,
      });
      setCreated(req);
      setStep(4);
    } catch (e) {
      setError(t(`errors.${apiErrorCode(e) ?? "unknown"}`));
    } finally {
      setBusy(false);
    }
  };

  const submitOtp = async () => {
    if (!token || !created) return;
    setBusy(true);
    setError(null);
    try {
      const done = await confirmReturn(token, created.id, otp.trim());
      router.push(`/account/returns/${done.id}`);
    } catch (e) {
      setError(t(`errors.${apiErrorCode(e) ?? "unknown"}`));
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    if (!token || !created) return;
    setNotice(null);
    try {
      await resendReturnOtp(token, created.id);
      setNotice(t("otpResent"));
    } catch (e) {
      setNotice(
        apiErrorCode(e) === "resend_cooldown"
          ? t("otpCooldown")
          : t("otpResendFailed")
      );
    }
  };

  return (
    <div className={styles.wizard}>
      <p className={styles.stepLabel}>{t("stepOf", { step, total: 4 })}</p>

      {step === 1 && (
        <section className={styles.card}>
          <h2 className={styles.heading}>{t("step1Title")}</h2>
          <p className={styles.muted}>{t("wholeLinesOnly")}</p>
          {eligibility.full_order_available && (
            <label className={styles.selectAll}>
              <input type="checkbox" checked={allSelected} onChange={selectAll} />
              <span>{t("returnEverything")}</span>
            </label>
          )}
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
                  <span className={styles.lineTotal}>₹{line.line_total.toFixed(2)}</span>
                </label>
                {!line.returnable && (
                  <p className={styles.lockNote}>
                    {t(`lock.${line.lock_reason ?? "unknown"}`)}
                  </p>
                )}
              </li>
            ))}
          </ul>
          {feeReturned && (
            <p className={styles.feeNote}>
              {t("feeReturned", { amount: eligibility.delivery_fee.toFixed(2) })}
            </p>
          )}
          <div className={styles.actions}>
            <button
              type="button"
              className="btn btn-primary"
              disabled={selected.length === 0}
              onClick={() => setStep(2)}
            >
              {t("next")}
            </button>
          </div>
        </section>
      )}

      {step === 2 && (
        <section className={styles.card}>
          <h2 className={styles.heading}>{t("step2Title")}</h2>
          <div className={styles.reasons}>
            {REASONS.map((code) => (
              <button
                key={code}
                type="button"
                className={`${styles.chip} ${reason === code ? styles.chipOn : ""}`}
                onClick={() => setReason(code)}
              >
                {t(`reason.${code}`)}
              </button>
            ))}
          </div>
          <label className={styles.label} htmlFor="return-note">
            {reason === "other" ? t("noteRequired") : t("noteOptional")}
          </label>
          <textarea
            id="return-note"
            className={styles.textarea}
            value={note}
            maxLength={500}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className={styles.actions}>
            <button type="button" className="btn" onClick={() => setStep(1)}>
              {t("back")}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={reason === "other" && !note.trim()}
              onClick={() => setStep(3)}
            >
              {t("next")}
            </button>
          </div>
        </section>
      )}

      {step === 3 && (
        <section className={styles.card}>
          <h2 className={styles.heading}>{t("step3Title")}</h2>
          <div className={styles.choices}>
            <button
              type="button"
              className={`${styles.choice} ${settlement === "store_credit" ? styles.choiceOn : ""}`}
              onClick={() => setSettlement("store_credit")}
            >
              <strong>{t("settlementCredit")}</strong>
              <span>{t("settlementCreditHint")}</span>
            </button>
            <button
              type="button"
              className={`${styles.choice} ${settlement === "payment" ? styles.choiceOn : ""}`}
              onClick={() => setSettlement("payment")}
            >
              <strong>{t("settlementPayment")}</strong>
              <span>{t("settlementPaymentHint")}</span>
            </button>
          </div>
          <p className={styles.muted}>{t("reversalNote")}</p>
          <div className={styles.actions}>
            <button type="button" className="btn" onClick={() => setStep(2)}>
              {t("back")}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={submitDraft}
              disabled={busy}
            >
              {t("next")}
            </button>
          </div>
          {error && (
            <p role="alert" className={styles.error}>
              {error}
            </p>
          )}
        </section>
      )}

      {step === 4 && created && (
        <section className={styles.card}>
          <h2 className={styles.heading}>{t("step4Title")}</h2>
          <dl className={styles.summary}>
            <div>
              <dt>{t("summaryItems")}</dt>
              <dd>₹{created.items_amount.toFixed(2)}</dd>
            </div>
            {created.delivery_fee_amount > 0 && (
              <div>
                <dt>{t("summaryDeliveryFee")}</dt>
                <dd>₹{created.delivery_fee_amount.toFixed(2)}</dd>
              </div>
            )}
            <div className={styles.summaryTotal}>
              <dt>{t("summaryTotal")}</dt>
              <dd>₹{created.total_amount.toFixed(2)}</dd>
            </div>
          </dl>
          {agreementBody && (
            <div className={styles.agreement}>
              <pre className={styles.agreementBody}>{agreementBody}</pre>
            </div>
          )}
          <label className={styles.acceptRow}>
            <input
              type="checkbox"
              checked={accepted}
              onChange={(e) => setAccepted(e.target.checked)}
            />
            <span>{t("acceptAgreement")}</span>
          </label>
          <label className={styles.label} htmlFor="return-otp">
            {t("otpLabel")}
          </label>
          <input
            id="return-otp"
            className={styles.otpInput}
            inputMode="numeric"
            maxLength={6}
            value={otp}
            onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
          />
          <button type="button" className={styles.linkButton} onClick={resend}>
            {t("otpResend")}
          </button>
          {notice && <p className={styles.muted}>{notice}</p>}
          <div className={styles.actions}>
            <button
              type="button"
              className="btn btn-primary"
              disabled={!accepted || otp.length !== 6 || busy}
              onClick={submitOtp}
            >
              {t("confirmReturn")}
            </button>
          </div>
          {error && (
            <p role="alert" className={styles.error}>
              {error}
            </p>
          )}
        </section>
      )}

      {/* Preview total is informational only; the server's number is binding. */}
      {step < 4 && selected.length > 0 && (
        <p className={styles.preview}>
          {t("previewTotal", { amount: previewTotal.toFixed(2) })}
        </p>
      )}
    </div>
  );
}
