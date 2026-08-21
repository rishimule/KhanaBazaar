"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import type { ReturnRequest, ReturnStatus } from "@/types";
import styles from "./ReturnTimeline.module.css";

/** The happy path. Terminal states other than `closed` are rendered as an
 *  end-stop rather than a step, because the return stopped there. */
const STEPS: ReturnStatus[] = [
  "awaiting_customer_confirmation",
  "active",
  "awaiting_payment_confirmation",
  "closed",
];

const STOPPED: ReturnStatus[] = ["rejected", "withdrawn", "expired"];

interface Props {
  request: ReturnRequest;
  namespace?: string;
}

export default function ReturnTimeline({
  request,
  namespace = "Account.returns",
}: Props) {
  const t = useTranslations(namespace);

  if (STOPPED.includes(request.status)) {
    return (
      <ol className={styles.timeline}>
        <li className={`${styles.step} ${styles.done}`}>
          {t("status.awaiting_customer_confirmation")}
        </li>
        <li className={`${styles.step} ${styles.stopped}`}>
          {t(`status.${request.status}`)}
        </li>
      </ol>
    );
  }

  // Whether a payment-confirmation step will ever happen is answered by two
  // different fields depending on how far the return has got:
  //   * before the seller accepts, no settlement has been computed, so every
  //     amount is still 0 and only the customer's CHOICE is meaningful;
  //   * once accepted, `payment_amount` is authoritative — a credit reversal
  //     can absorb the whole amount, closing the return with nothing to pay
  //     even though the customer asked for money back.
  // Keying on the choice alone left a step that could never complete; keying on
  // the amount alone would hide the step from a customer who is still waiting.
  const settled =
    request.status === "awaiting_payment_confirmation" ||
    request.status === "closed";
  const expectsPayment = settled
    ? request.payment_amount > 0
    : request.settlement_choice === "payment";
  const steps = STEPS.filter(
    (s) => s !== "awaiting_payment_confirmation" || expectsPayment
  );
  const currentIndex = steps.indexOf(request.status);

  return (
    <ol className={styles.timeline}>
      {steps.map((step, i) => (
        <li
          key={step}
          className={[
            styles.step,
            i < currentIndex ? styles.done : "",
            i === currentIndex ? styles.current : "",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          {t(`status.${step}`)}
        </li>
      ))}
    </ol>
  );
}
