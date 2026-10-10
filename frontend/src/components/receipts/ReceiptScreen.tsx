// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { apiErrorCode } from "@/lib/errors";
import { formatReceiptDate, getOrderReceipt } from "@/lib/receipts";
import type { Receipt, ReturnStatus } from "@/types";
import ReceiptDocument from "./ReceiptDocument";
import styles from "./ReceiptDocument.module.css";

type State =
  | { kind: "loading" }
  | { kind: "ready"; receipt: Receipt }
  | { kind: "notIssued" }
  | { kind: "notDelivered" }
  | { kind: "error" };

interface Props {
  orderId: number;
  orderHref: string;
  sellerCopy?: boolean;
  /** Each surface renders links with its own Link (next-intl on the
   *  storefront so the locale prefix survives, next/link for operators). */
  renderLink: (href: string, label: string, className?: string) => ReactNode;
  returnHref: (returnId: number) => string;
  returnStatusLabel: (status: ReturnStatus) => string;
}

export default function ReceiptScreen({
  orderId,
  orderHref,
  sellerCopy = false,
  renderLink,
  returnHref,
  returnStatusLabel,
}: Props) {
  const t = useTranslations("Receipt");
  const locale = useLocale();
  const { token } = useAuth();
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    if (!token) return;
    let live = true;
    getOrderReceipt(token, orderId)
      .then((receipt) => {
        if (live) setState({ kind: "ready", receipt });
      })
      .catch((e: unknown) => {
        if (!live) return;
        const code = apiErrorCode(e);
        // A silent refetch (token rotation) must not hide a receipt already shown.
        setState((prev) => {
          if (prev.kind === "ready") return prev;
          if (code === "receipt_not_issued") return { kind: "notIssued" };
          if (code === "order_not_delivered") return { kind: "notDelivered" };
          return { kind: "error" };
        });
      });
    return () => {
      live = false;
    };
  }, [token, orderId]);

  const later = state.kind === "ready" ? state.receipt.later_changes : null;
  const hasLater = later !== null && (later.refunded_at !== null || later.returns.length > 0);

  return (
    <div className={styles.screen}>
      <div className={`${styles.toolbar} kb-no-print`}>
        {renderLink(orderHref, t("backToOrder"), "btn")}
        {state.kind === "ready" && (
          <button type="button" className="btn btn-primary" onClick={() => window.print()}>
            {t("print")}
          </button>
        )}
      </div>

      {state.kind === "loading" && (
        <p className={styles.status} role="status">
          {t("loading")}
        </p>
      )}
      {state.kind === "notIssued" && (
        <p className={styles.status} role="status">
          {t("notIssued")}
        </p>
      )}
      {state.kind === "notDelivered" && (
        <p className={styles.status} role="status">
          {t("notDelivered")}
        </p>
      )}
      {state.kind === "error" && (
        <p className={styles.status} role="alert">
          {t("loadError")}
        </p>
      )}

      {state.kind === "ready" && (
        <ReceiptDocument receipt={state.receipt} sellerCopy={sellerCopy} />
      )}
      {later && hasLater && (
        <aside className={`${styles.later} kb-receipt-print`}>
          <h2 className={styles.label}>{t("laterTitle")}</h2>
          <ul>
            {later.refunded_at && (
              <li>
                {t("laterRefunded", {
                  date: formatReceiptDate(later.refunded_at, locale, false),
                })}
              </li>
            )}
            {later.returns.map((r) => (
              <li key={r.id}>
                {renderLink(
                  returnHref(r.id),
                  t("laterReturn", { id: r.id, status: returnStatusLabel(r.status) }),
                )}
              </li>
            ))}
          </ul>
        </aside>
      )}
    </div>
  );
}
