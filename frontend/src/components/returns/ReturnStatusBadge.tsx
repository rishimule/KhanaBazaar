"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import type { ReturnStatus } from "@/types";
import styles from "./ReturnStatusBadge.module.css";

/** Tone per resting state. `active` and the two awaiting states are "in
 *  flight"; only `closed` is a success. */
const TONE: Record<ReturnStatus, string> = {
  awaiting_customer_confirmation: "waiting",
  active: "progress",
  awaiting_payment_confirmation: "waiting",
  closed: "done",
  rejected: "bad",
  withdrawn: "muted",
  expired: "muted",
};

interface Props {
  status: ReturnStatus;
  /** i18n namespace holding `status.<value>` keys. */
  namespace?: string;
}

export default function ReturnStatusBadge({
  status,
  namespace = "Account.returns",
}: Props) {
  const t = useTranslations(namespace);
  return (
    <span className={`${styles.badge} ${styles[TONE[status]]}`}>
      {t(`status.${status}`)}
    </span>
  );
}
