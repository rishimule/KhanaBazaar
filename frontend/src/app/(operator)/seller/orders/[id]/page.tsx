"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { use, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { getOrder } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import OrderTimeline from "@/components/orders/OrderTimeline";
import OrderItemList from "@/components/orders/OrderItemList";
import OrderActionButtons from "@/components/orders/OrderActionButtons";
import OrderStatusBadge from "@/components/orders/OrderStatusBadge";
import { DeliveryRouteMap } from "@/components/orders/DeliveryRouteMap";
import RequestedDeliveryLine from "@/components/orders/RequestedDeliveryLine";
import type { Order } from "@/types";
import styles from "./page.module.css";

export default function SellerOrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("Seller.orderDetail");
  const tc = useTranslations("Seller.common");
  const tp = useTranslations("Shared.paymentStatus");
  const { token } = useAuth();
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    getOrder(token, Number(id))
      .then(setOrder)
      .catch((e: { detail?: string }) => setError(e?.detail ?? t("loadError")));
  }, [token, id, t]);

  if (error) return <div className={styles.error}>{error}</div>;
  if (!order) return <div className={styles.loading}>{tc("loading")}</div>;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>{t("title", { id: order.id })}</h1>
        <OrderStatusBadge status={order.status} />
      </div>
      {order.customer_name && (
        <p className={styles.subtitle}>
          {t("forCustomer", { name: order.customer_name })}{" "}
          <span className={styles.serviceChip}>· {order.service_name}</span>
        </p>
      )}
      <RequestedDeliveryLine order={order} className={styles.subtitle} />

      <section className={styles.section}>
        <OrderTimeline status={order.status} />
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{t("items")}</h2>
        <OrderItemList items={order.items} />
        <div className={styles.totals}>
          <div><span>{t("subtotal")}</span><span>₹{order.subtotal.toFixed(2)}</span></div>
          <div><span>{t("delivery")}</span><span>₹{order.delivery_fee.toFixed(2)}</span></div>
          <div><span>{t("tax")}</span><span>₹{order.tax.toFixed(2)}</span></div>
          <div className={styles.grand}><span>{t("total")}</span><span>₹{order.total.toFixed(2)}</span></div>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{t("payment")}</h2>
        <p>{order.payment.method.toUpperCase()} · {tp(order.payment.status)}</p>
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
