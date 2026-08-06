"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Modal from "@/components/Modal";
import styles from "./PlanExitConfirmModal.module.css";

interface Props {
  title: string;
  /** What the customer-facing consequence is. Rendered in danger tone. */
  consequence: string;
  /** What happens to the seller's money. */
  money: string;
  /** How the seller gets back to live. */
  recovery: string;
  keepLabel: string;
  confirmLabel: string;
  busy: boolean;
  onKeep: () => void;
  onConfirm: () => void;
}

/** Confirmation for a seller action that hides a service from customers.
 *  Never a window.confirm: the consequence, the money and the way back all
 *  have to be readable before the tap (seller UX audit BLOCKER #2/#3/#8).
 *
 *  The action row lives in `children`, not Modal's `footer` prop: that footer
 *  is `justify-content: flex-end` at every width, and these two labels are too
 *  long to sit side by side at 375px. Owning the row here lets it stack
 *  full-width on the bottom-sheet breakpoint (matching the Figma frames) while
 *  staying inside Modal's focus trap, which wraps body and footer alike. */
export default function PlanExitConfirmModal({
  title,
  consequence,
  money,
  recovery,
  keepLabel,
  confirmLabel,
  busy,
  onKeep,
  onConfirm,
}: Props) {
  return (
    <Modal title={title} size="sheet" onClose={onKeep}>
      <p className={styles.consequence} role="alert">
        {consequence}
      </p>
      <p className={styles.line}>{money}</p>
      <p className={styles.line}>{recovery}</p>
      <div className={styles.actions}>
        <button type="button" className={styles.keep} onClick={onKeep}>
          {keepLabel}
        </button>
        <button type="button" className={styles.danger} disabled={busy} onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
