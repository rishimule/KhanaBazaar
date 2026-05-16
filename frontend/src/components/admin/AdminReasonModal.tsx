"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useState } from "react";
import Modal from "@/components/Modal";
import styles from "./AdminReasonModal.module.css";

interface Props {
  title: string;
  /** Optional explanation rendered above the textarea. */
  description?: string;
  confirmLabel?: string;
  destructive?: boolean;
  onConfirm: (reason: string) => Promise<void> | void;
  onClose: () => void;
}

export default function AdminReasonModal({
  title,
  description,
  confirmLabel = "Confirm",
  destructive = true,
  onConfirm,
  onClose,
}: Props) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const trimmedLen = reason.trim().length;
  const canSubmit = trimmedLen >= 10 && !busy;

  async function submit() {
    if (!canSubmit) return;
    setBusy(true);
    try {
      await onConfirm(reason.trim());
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={title}
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-outline" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            className={destructive ? "btn btn-danger" : "btn btn-primary"}
            disabled={!canSubmit}
            onClick={submit}
          >
            {busy ? "…" : confirmLabel}
          </button>
        </>
      }
    >
      {description && <p className={styles.description}>{description}</p>}
      <label className={styles.label}>
        Reason
        <textarea
          className={styles.textarea}
          rows={4}
          maxLength={500}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Minimum 10 characters — used in the audit log and emailed to the seller."
        />
      </label>
      <div className={styles.counter}>
        {trimmedLen} / 500 ({trimmedLen < 10 ? "need 10+ chars" : "ok"})
      </div>
    </Modal>
  );
}
