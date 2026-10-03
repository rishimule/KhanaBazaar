"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { getOrder } from "@/lib/orders";
import { formatDeliveryEta } from "@/lib/deliveryEta";
import { useAuth } from "@/lib/AuthContext";
import RequestedDeliveryLine from "@/components/orders/RequestedDeliveryLine";
import UpiPayPanel from "@/components/orders/UpiPayPanel";
import OrderTotal from "@/components/orders/OrderTotal";
import type { Order } from "@/types";
import styles from "./page.module.css";

export default function OrderConfirmedPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { token, loading: authLoading } = useAuth();
  const t = useTranslations("OrderConfirmed");
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!token) return;
    getOrder(token, Number(id)).then(setOrder).catch(() => setError(true));
  }, [token, id]);

  // No session once auth has settled (guest / expired / logged out elsewhere):
  // show the error instead of an infinite spinner.
  if (error || (!authLoading && !token))
    return <div className={styles.state} role="alert">{t("loadError")}</div>;
  if (!order)
    return <div className={styles.state} role="status" aria-busy="true">{t("loading")}</div>;

  const itemCount = order.items.reduce((n, it) => n + it.quantity, 0);
  // Courier: the store quotes the charge and dates next, nothing is payable yet.
  const isCourier = order.delivery_mode === "courier";

  return (
    <div className={styles.wrap}>
      <div className={styles.check} aria-hidden>✓</div>
      <h1 className={styles.title}>{isCourier ? t("courierTitle") : t("title")}</h1>
      <p className={styles.subtitle}>
        {isCourier ? t("courierSubtitle", { store: order.store_name }) : t("subtitle")}
      </p>

      <div className={styles.card}>
        <div className={styles.orderNo}>{t("orderNumber", { id: order.id })}</div>
        <div className={styles.store}>
          {order.store_name} · {order.service_name}
        </div>
        {!isCourier &&
          order.delivery_eta_min_minutes != null &&
          order.delivery_eta_max_minutes != null && (
          <div className={styles.row}>
            <span>{t("estimatedDelivery")}</span>
            <span>{formatDeliveryEta(order.delivery_eta_min_minutes, order.delivery_eta_max_minutes)}</span>
          </div>
        )}
        <RequestedDeliveryLine order={order} className={styles.requested} />
        <div className={styles.row}>
          <span>{t("itemsCount", { count: itemCount })}</span>
          <OrderTotal order={order} className={styles.total} />
        </div>
      </div>

      <UpiPayPanel order={order} onChange={setOrder} />

      <div className={styles.actions}>
        <Link href={`/account/orders/${order.id}`} className="btn btn-primary">{t("trackOrder")}</Link>
        <Link href="/" className="btn btn-secondary">{t("continueShopping")}</Link>
      </div>
    </div>
  );
}
