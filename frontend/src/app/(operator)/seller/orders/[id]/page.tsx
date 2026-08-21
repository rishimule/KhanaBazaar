"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { use, useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { getOrder } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import OrderTimeline from "@/components/orders/OrderTimeline";
import OrderItemList from "@/components/orders/OrderItemList";
import OrderActionButtons from "@/components/orders/OrderActionButtons";
import OrderStatusBadge from "@/components/orders/OrderStatusBadge";
import { DeliveryRouteMap } from "@/components/orders/DeliveryRouteMap";
import RequestedDeliveryLine from "@/components/orders/RequestedDeliveryLine";
import LoadError from "@/components/LoadError";
import Link from "next/link";
import type { Order } from "@/types";
import styles from "./page.module.css";

export default function SellerOrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("Seller.orderDetail");
  const tc = useTranslations("Seller.common");
  const tp = useTranslations("Shared.paymentStatus");
  const tpm = useTranslations("Order.payment.method");
  const { token } = useAuth();
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState<unknown>(null);

  // Generation guard: `error` is checked before `order` in the render, so a
  // rejection from an older in-flight request landing after a newer success
  // would pin the page on LoadError while holding good data. Reachable by
  // double-tapping Retry on a flaky connection, or by a token refresh
  // restarting the fetch mid-flight.
  const reqId = useRef(0);

  const load = useCallback(() => {
    if (!token) return;
    const mine = ++reqId.current;
    getOrder(token, Number(id))
      .then((next) => {
        if (mine !== reqId.current) return;
        setOrder(next);
        setError(null);
      })
      .catch((e: unknown) => {
        if (mine !== reqId.current) return;
        setError(e);
      });
  }, [token, id]);

  useEffect(() => {
    load();
  }, [load]);

  if (error != null) return <LoadError error={error} onRetry={load} title={t("loadError")} />;
  if (!order) return <div className={styles.loading}>{tc("loading")}</div>;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>{t("title", { id: order.id })}</h1>
        <OrderStatusBadge status={order.status} deliveryMode={order.delivery_mode} />
      </div>
      {order.customer_name && (
        <p className={styles.subtitle}>
          {t("forCustomer", { name: order.customer_name })}{" "}
          <span className={styles.serviceChip}>· {order.service_name}</span>
        </p>
      )}
      <RequestedDeliveryLine order={order} className={styles.subtitle} />

      <section className={styles.section}>
        <OrderTimeline status={order.status} deliveryMode={order.delivery_mode} />
      </section>

      {/* Returns can only start from a delivered order; the backend enforces
          the window, so this is an entry point, not the eligibility check. */}
      {order.status === "delivered" && (
        <section className={styles.section}>
          <Link className="btn" href={`/seller/orders/${order.id}/return`}>
            {t("startReturn")}
          </Link>
        </section>
      )}

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{t("items")}</h2>
        <OrderItemList items={order.items} />
        <div className={styles.totals}>
          <div><span>{t("subtotal")}</span><span>₹{order.subtotal.toFixed(2)}</span></div>
          <div><span>{t("delivery")}</span><span>₹{order.delivery_fee.toFixed(2)}</span></div>
          <div><span>{t("tax")}</span><span>₹{order.tax.toFixed(2)}</span></div>
          <div className={styles.grand}><span>{t("total")}</span><span>₹{order.total.toFixed(2)}</span></div>
          {(order.store_credit_applied ?? 0) > 0 && (
            <>
              <div><span>{t("storeCreditApplied")}</span><span>−₹{(order.store_credit_applied ?? 0).toFixed(2)}</span></div>
              {/* What to actually collect. Showing only the gross total here
                  makes a COD agent over-collect by the credit amount. */}
              <div className={styles.grand}><span>{t("amountPayable")}</span><span>₹{order.payment.amount.toFixed(2)}</span></div>
            </>
          )}
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{t("payment")}</h2>
        <p>{tpm(order.payment.method)} · {tp(order.payment.status)}</p>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{t("deliveryTo")}</h2>
        <p>{order.delivery_address_snapshot}</p>
        {order.store_latitude != null &&
          order.store_longitude != null &&
          order.delivery_latitude != null &&
          order.delivery_longitude != null && (
            <DeliveryRouteMap
              store={{
                lat: order.store_latitude,
                lng: order.store_longitude,
                label: order.store_name,
              }}
              customer={{
                lat: order.delivery_latitude,
                lng: order.delivery_longitude,
                label: order.customer_name ?? t("customerFallback"),
              }}
            />
          )}
      </section>

      <section className={styles.section}>
        <OrderActionButtons order={order} role="seller" onChange={setOrder} />
      </section>
    </div>
  );
}
