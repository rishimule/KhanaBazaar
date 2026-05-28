"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import type { SellerProfileChangeRequestEvent } from "@/types";
import styles from "./ChangeRequestTimeline.module.css";

interface Props {
  events: SellerProfileChangeRequestEvent[];
}

function ts(s: string): string {
  const d = new Date(s);
  return d.toLocaleString();
}

/**
 * Vertical event log for a single change request — submissions,
 * admin actions, and terminal transitions. Stateless / pure.
 */
export default function ChangeRequestTimeline({ events }: Props) {
  const t = useTranslations("Shared.changeRequest");
  return (
    <ol className={styles.timeline}>
      {events.map((e) => (
        <li key={e.id} className={styles.item}>
          <span className={styles.kind}>{t(`kind_${e.kind}`)}</span>
          <span className={styles.time}>{ts(e.created_at)}</span>
          {e.note && <p className={styles.note}>{e.note}</p>}
        </li>
      ))}
    </ol>
  );
}
