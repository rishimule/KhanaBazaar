"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useState } from "react";
import Modal from "@/components/Modal";

interface Props {
  busy?: boolean;
  onConfirm: (payload: { reason?: string; paused_until?: string }) => void;
  onClose: () => void;
}

/** Returns today's date as YYYY-MM-DD in the local timezone, for the date
 *  input's `min` (a reopen date can't be in the past). */
function todayISO(): string {
  const d = new Date();
  const tzOffset = d.getTimezoneOffset() * 60000;
  return new Date(d.getTime() - tzOffset).toISOString().slice(0, 10);
}

export default function CloseStoreModal({ busy, onConfirm, onClose }: Props) {
  const [reason, setReason] = useState("");
  const [reopenDate, setReopenDate] = useState("");

  const submit = () => {
    onConfirm({
      reason: reason.trim() || undefined,
      paused_until: reopenDate || undefined,
    });
  };

  return (
    <Modal
      title="Close store"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-outline" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={submit} disabled={busy}>
            {busy ? "…" : "Close store"}
          </button>
        </>
      }
    >
      <p style={{ color: "var(--color-neutral-600)", marginBottom: "1rem" }}>
        Your store stays visible to customers but won&apos;t take new orders until you
        reopen it. Orders already placed are unaffected.
      </p>
      <label style={{ display: "block", marginBottom: "1rem" }}>
        <span style={{ display: "block", marginBottom: "0.35rem", fontWeight: 500 }}>
          Reopening on <span style={{ color: "var(--color-neutral-500)" }}>(optional)</span>
        </span>
        <input
          type="date"
          value={reopenDate}
          min={todayISO()}
          onChange={(e) => setReopenDate(e.target.value)}
          style={{
            width: "100%",
            padding: "0.5rem",
            border: "1px solid var(--color-neutral-300)",
            borderRadius: 6,
          }}
        />
        <span
          style={{
            display: "block",
            marginTop: "0.3rem",
            fontSize: "0.8rem",
            color: "var(--color-neutral-500)",
          }}
        >
          Shown to customers as &ldquo;Closed — back &lt;date&gt;&rdquo;. You still reopen
          the store manually; this date never reopens it automatically.
        </span>
      </label>
      <label style={{ display: "block" }}>
        <span style={{ display: "block", marginBottom: "0.35rem", fontWeight: 500 }}>
          Reason <span style={{ color: "var(--color-neutral-500)" }}>(optional)</span>
        </span>
        <input
          type="text"
          value={reason}
          maxLength={200}
          placeholder="e.g. Diwali holidays"
          onChange={(e) => setReason(e.target.value)}
          style={{
            width: "100%",
            padding: "0.5rem",
            border: "1px solid var(--color-neutral-300)",
            borderRadius: 6,
          }}
        />
      </label>
    </Modal>
  );
}
