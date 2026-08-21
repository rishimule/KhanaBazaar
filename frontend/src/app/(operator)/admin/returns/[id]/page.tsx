"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { use, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AdminReturnActions from "@/components/returns/AdminReturnActions";
import ReturnStatusBadge from "@/components/returns/ReturnStatusBadge";
import { useAuth } from "@/lib/AuthContext";
import { adminGetReturn } from "@/lib/returns";
import type { ReturnRequest } from "@/types";
import styles from "./page.module.css";

export default function AdminReturnDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const returnId = Number(id);
  const t = useTranslations("Admin.returns");
  const { token } = useAuth();
  const [request, setRequest] = useState<ReturnRequest | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await adminGetReturn(token, returnId);
        if (!cancelled) setRequest(data);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, returnId]);

  if (failed) {
    return (
      <p role="alert" className={styles.error}>
        {t("loadFailed")}
      </p>
    );
  }
  if (!request) return <p className={styles.muted}>{t("loading")}</p>;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>
          {t("detailTitle", { id: request.id, orderId: request.order_id })}
        </h1>
        <ReturnStatusBadge status={request.status} namespace="Admin.returns" />
      </header>

      <section className={styles.card}>
        <dl className={styles.grid}>
          <dt>{t("colSeller")}</dt>
          <dd>#{request.seller_profile_id}</dd>
          <dt>{t("fieldInitiatedBy")}</dt>
          <dd>{t(`initiator.${request.initiated_by}`)}</dd>
          <dt>{t("fieldReason")}</dt>
          <dd>
            {t(`reason.${request.reason_code}`)}
            {request.reason_note ? ` — ${request.reason_note}` : ""}
          </dd>
          <dt>{t("colAmount")}</dt>
          <dd>₹{request.total_amount.toFixed(2)}</dd>
          <dt>{t("fieldSettlement")}</dt>
          <dd>
            {t(
              request.settlement_choice === "store_credit"
                ? "settlementCredit"
                : "settlementPayment"
            )}
          </dd>
          {request.credit_reversal_amount > 0 && (
            <>
              <dt>{t("fieldReversal")}</dt>
              <dd>₹{request.credit_reversal_amount.toFixed(2)}</dd>
            </>
          )}
          {request.rejection_reason && (
            <>
              <dt>{t("fieldRejectionReason")}</dt>
              <dd>{request.rejection_reason}</dd>
            </>
          )}
        </dl>
      </section>

      <section className={styles.card}>
        <h2 className={styles.heading}>{t("itemsTitle")}</h2>
        <ul className={styles.items}>
          {request.items.map((item) => (
            <li key={item.order_item_id}>
              <span>
                {item.product_name} × {item.quantity}
              </span>
              <span>₹{item.line_total.toFixed(2)}</span>
            </li>
          ))}
        </ul>
      </section>

      <AdminReturnActions request={request} onChange={setRequest} />
    </div>
  );
}
