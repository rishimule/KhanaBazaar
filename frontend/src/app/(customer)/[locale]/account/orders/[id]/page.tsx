"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { use, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { getOrder } from "@/lib/orders";
import { formatDeliveryEta } from "@/lib/deliveryEta";
import { useAuth } from "@/lib/AuthContext";
import { apiErrorKey } from "@/lib/errors";
import OrderTimeline from "@/components/orders/OrderTimeline";
import DeliveryOtpPanel from "@/components/orders/DeliveryOtpPanel";
import OrderItemList from "@/components/orders/OrderItemList";
import OrderActionButtons from "@/components/orders/OrderActionButtons";
import ReorderButton from "@/components/orders/ReorderButton";
import OrderStatusBadge from "@/components/orders/OrderStatusBadge";
import PaymentStatusBadge from "@/components/orders/PaymentStatusBadge";
import { DeliveryRouteMap } from "@/components/orders/DeliveryRouteMap";
import type { Order } from "@/types";
import styles from "./page.module.css";

export default function CustomerOrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { token } = useAuth();
  const t = useTranslations("Account.orderDetail");
  const tErr = useTranslations("Errors");
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    getOrder(token, Number(id))
      .then(setOrder)
      .catch((e: unknown) => {
        const key = apiErrorKey(e);
        if (key) {
          setError(tErr(key.replace(/^Errors\./, "")));
        } else {
          const detail = (e as { detail?: string })?.detail;
          setError(detail ?? t("loadError"));
        }
      });
  }, [token, id, t, tErr]);

  if (error) return <div className={styles.error}>{error}</div>;
  if (!order) return <div className={styles.loading}>{t("loading")}</div>;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>{t("title", { id: order.id })}</h1>
        <OrderStatusBadge status={order.status} />
      </div>
      <p className={styles.subtitle}>
        {order.store_name} <span className={styles.serviceChip}>· {order.service_name}</span>
      </p>
      {order.delivery_eta_min_minutes != null && order.delivery_eta_max_minutes != null && (
        <p className={styles.subtitle}>
          {t("estimatedDelivery")}:{" "}
          {formatDeliveryEta(order.delivery_eta_min_minutes, order.delivery_eta_max_minutes)}
        </p>
      )}

      <section className={styles.section}>
        <OrderTimeline status={order.status} />
      </section>

      <DeliveryOtpPanel order={order} onChange={setOrder} />

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{t("items")}</h2>
        <OrderItemList items={order.items} />
        <div className={styles.totals}>
          <div><span>{t("subtotal")}</span><span>{t("amount", { amount: order.subtotal.toFixed(2) })}</span></div>
          <div><span>{t("delivery")}</span><span>{t("amount", { amount: order.delivery_fee.toFixed(2) })}</span></div>
          <div><span>{t("tax")}</span><span>{t("amount", { amount: order.tax.toFixed(2) })}</span></div>
          <div className={styles.grand}><span>{t("total")}</span><span>{t("amount", { amount: order.total.toFixed(2) })}</span></div>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{t("payment")}</h2>
        <p>{order.payment.method.toUpperCase()} · <PaymentStatusBadge status={order.payment.status} /></p>
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
                label: "Your address",
              }}
            />
          )}
      </section>

      <section className={styles.section}>
        <div className={styles.actionRow}>
          <ReorderButton orderId={order.id} className={styles.reorderBtn} />
          <OrderActionButtons order={order} role="customer" onChange={setOrder} />
        </div>
      </section>
    </div>
  );
}
