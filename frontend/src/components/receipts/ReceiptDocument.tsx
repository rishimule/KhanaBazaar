// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useId } from "react";
import { useLocale, useTranslations } from "next-intl";
import { formatReceiptDate, money, receiptPaymentKey } from "@/lib/receipts";
import type { Receipt } from "@/types";
import styles from "./ReceiptDocument.module.css";

/** The receipt itself: exactly what was frozen at issue time. The
 *  `kb-receipt-print` class is what globals.css keeps when printing. */
export default function ReceiptDocument({
  receipt,
  sellerCopy = false,
}: {
  receipt: Receipt;
  sellerCopy?: boolean;
}) {
  const t = useTranslations("Receipt");
  const locale = useLocale();
  const titleId = useId();
  const s = receipt.snapshot;
  const isPickup = s.order.delivery_mode === "pickup";
  const to = s.deliver_to;
  // Spec §3.2: a door/courier block with nothing recorded is skipped.
  const hasDeliverTo = isPickup || Boolean(to && (to.name || to.phone || to.address));
  const recipient = to ? [to.name, to.phone].filter(Boolean).join(" · ") : "";
  const amount = (n: number) => t("amount", { amount: money(n) });

  return (
    <article className={`${styles.receipt} kb-receipt-print`} aria-labelledby={titleId}>
      <header className={styles.head}>
        <div>
          {sellerCopy && <p className={styles.copyLabel}>{t("sellerCopy")}</p>}
          <h2 id={titleId} className={styles.title}>
            {t("title")}
          </h2>
          <p className={styles.meta}>{t("number", { number: receipt.number })}</p>
          <p className={styles.meta}>
            {t(isPickup ? "headline.collected" : "headline.delivered", {
              date: formatReceiptDate(receipt.issued_at, locale),
            })}
          </p>
          {receipt.issued_via === "backfill" && (
            <p className={styles.note}>
              {t("reissued", { date: formatReceiptDate(receipt.created_at, locale, false) })}
            </p>
          )}
        </div>
        <div className={styles.orderRef}>
          <p>{t("orderRef", { id: s.order.id, service: s.order.service_name })}</p>
          <p className={styles.meta}>
            {t("placedOn", { date: formatReceiptDate(s.order.placed_at, locale) })}
          </p>
        </div>
      </header>

      <section className={styles.parties}>
        <div>
          <h3 className={styles.label}>{t("soldBy")}</h3>
          <p className={styles.strong}>{s.seller.business_name}</p>
          <p>{s.seller.store_name}</p>
          {s.seller.store_address && <p>{s.seller.store_address}</p>}
          {s.seller.gstin && <p>{t("gstin", { value: s.seller.gstin })}</p>}
          {s.seller.fssai && <p>{t("fssai", { value: s.seller.fssai })}</p>}
        </div>
        <div>
          <h3 className={styles.label}>{t("billedTo")}</h3>
          <p className={styles.strong}>{s.customer.name}</p>
          {s.customer.phone && <p>{s.customer.phone}</p>}
          {hasDeliverTo && (
            <>
              <h3 className={`${styles.label} ${styles.labelGap}`}>
                {isPickup ? t("collectedAtLabel") : t("deliveredTo")}
              </h3>
              {isPickup ? (
                <p>{s.seller.store_name}</p>
              ) : (
                <>
                  {recipient && <p>{recipient}</p>}
                  {to?.address && <p>{to.address}</p>}
                </>
              )}
            </>
          )}
        </div>
      </section>

      <table className={styles.items}>
        <thead>
          <tr>
            <th scope="col">{t("item")}</th>
            <th scope="col" className={styles.num}>{t("qty")}</th>
            <th scope="col" className={styles.num}>{t("unitPrice")}</th>
            <th scope="col" className={styles.num}>{t("lineTotal")}</th>
          </tr>
        </thead>
        <tbody>
          {s.items.map((item, i) => (
            <tr key={i}>
              <td className={styles.itemName}>{item.name}</td>
              <td className={styles.num}>{item.quantity}</td>
              <td className={styles.num}>{amount(item.unit_price)}</td>
              <td className={styles.num}>{amount(item.line_total)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <dl className={styles.totals}>
        <div>
          <dt>{t("subtotal")}</dt>
          <dd>{amount(s.amounts.subtotal)}</dd>
        </div>
        {!isPickup && (
          <div>
            <dt>
              {s.amounts.delivery_fee_kind === "courier" ? t("courierCharge") : t("deliveryFee")}
            </dt>
            <dd>{s.amounts.delivery_fee > 0 ? amount(s.amounts.delivery_fee) : t("free")}</dd>
          </div>
        )}
        <div className={styles.grand}>
          <dt>{t("total")}</dt>
          <dd>{amount(s.amounts.total)}</dd>
        </div>
        {s.amounts.store_credit_applied > 0 && (
          <div>
            <dt>{t("storeCreditUsed")}</dt>
            <dd>{t("minusAmount", { amount: money(s.amounts.store_credit_applied) })}</dd>
          </div>
        )}
      </dl>

      <p className={styles.payment}>
        {t(`payment.${receiptPaymentKey(s)}`, {
          amount: money(s.amounts.amount_paid),
          method: s.payment.method ? t(`method.${s.payment.method}`) : "",
          store: s.seller.store_name,
        })}
      </p>
      <p className={styles.footer}>{t("notTaxInvoice")}</p>
    </article>
  );
}
