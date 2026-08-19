"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { apiErrorCode } from "@/lib/errors";
import {
  adminForceAccept,
  adminForceClose,
  adminForceReject,
} from "@/lib/returns";
import type { ReturnRequest } from "@/types";
import styles from "./AdminReturnActions.module.css";

/** Matches the server rule, so the operator is never surprised by a 422. */
const MIN_REASON = 10;

type Action = "accept" | "reject" | "close";

interface Props {
  request: ReturnRequest;
  onChange: (next: ReturnRequest) => void;
}

/**
 * Force paths. These bypass the seller's handover OTP — never the customer's
 * consent OTP — so they exist to unstick a return, not to manufacture consent.
 */
export default function AdminReturnActions({ request, onChange }: Props) {
  const t = useTranslations("Admin.returns");
  const { token } = useAuth();
  const [action, setAction] = useState<Action | null>(null);
  const [reason, setReason] = useState("");
  const [restock, setRestock] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const terminal = ["closed", "rejected", "withdrawn", "expired"].includes(
    request.status
  );
  if (terminal) return null;

  const submit = async () => {
    if (!token || !action) return;
    setBusy(true);
    setError(null);
    try {
      const next =
        action === "accept"
          ? await adminForceAccept(token, request.id, reason.trim(), restock)
          : action === "reject"
            ? await adminForceReject(token, request.id, reason.trim())
            : await adminForceClose(token, request.id, reason.trim());
      onChange(next);
      setAction(null);
      setReason("");
    } catch (e) {
      setError(t(`errors.${apiErrorCode(e) ?? "unknown"}`));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={styles.card}>
      <h3 className={styles.heading}>{t("forceTitle")}</h3>
      <p className={styles.muted}>{t("forceHint")}</p>

      <div className={styles.buttons}>
        {(["accept", "reject", "close"] as Action[]).map((a) => (
          <button
            key={a}
            type="button"
            className={`${styles.action} ${action === a ? styles.actionOn : ""}`}
            disabled={a === "accept" && request.status !== "active"}
            onClick={() => setAction(action === a ? null : a)}
          >
            {t(`force.${a}`)}
          </button>
        ))}
      </div>

      {action && (
        <div className={styles.modal}>
          <label className={styles.label} htmlFor="admin-return-reason">
            {t("reasonLabel")}
          </label>
          <textarea
            id="admin-return-reason"
            className={styles.textarea}
            value={reason}
            maxLength={500}
            onChange={(e) => setReason(e.target.value)}
          />
          <p className={styles.hint}>
            {t("reasonMin", { min: MIN_REASON })}
          </p>
          {action === "accept" && (
            <label className={styles.checkboxRow}>
              <input
                type="checkbox"
                checked={restock}
                onChange={(e) => setRestock(e.target.checked)}
              />
              <span>{t("restockLabel")}</span>
            </label>
          )}
          <div className={styles.modalActions}>
            <button
              type="button"
              className="btn btn-primary"
              disabled={reason.trim().length < MIN_REASON || busy}
              onClick={submit}
            >
              {t(`confirm.${action}`)}
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => setAction(null)}
            >
              {t("cancel")}
            </button>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      )}
    </section>
  );
}
