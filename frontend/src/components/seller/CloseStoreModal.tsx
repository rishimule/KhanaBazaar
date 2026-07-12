"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useState } from "react";
import { useTranslations } from "next-intl";
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
  const t = useTranslations("Seller.dashboard");
  const tc = useTranslations("Seller.common");
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
      title={t("closeStore")}
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-outline" onClick={onClose} disabled={busy}>
            {tc("cancel")}
          </button>
          <button className="btn btn-primary" onClick={submit} disabled={busy}>
            {busy ? "…" : t("closeStore")}
          </button>
        </>
      }
    >
      <p style={{ color: "var(--color-neutral-600)", marginBottom: "1rem" }}>
        {t("closeStoreBody")}
      </p>
      <label style={{ display: "block", marginBottom: "1rem" }}>
        <span style={{ display: "block", marginBottom: "0.35rem", fontWeight: 500 }}>
          {t("reopenOn")} <span style={{ color: "var(--color-neutral-500)" }}>{t("optional")}</span>
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
          {t("reopenHint")}
        </span>
      </label>
      <label style={{ display: "block" }}>
        <span style={{ display: "block", marginBottom: "0.35rem", fontWeight: 500 }}>
          {t("reason")} <span style={{ color: "var(--color-neutral-500)" }}>{t("optional")}</span>
        </span>
        <input
          type="text"
          value={reason}
          maxLength={200}
          placeholder={t("reasonPlaceholder")}
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
