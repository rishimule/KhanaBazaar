"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { use, useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { getOrder } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import OrderTimeline from "@/components/orders/OrderTimeline";
import DeliveryOtpPanel from "@/components/orders/DeliveryOtpPanel";
import OrderItemList from "@/components/orders/OrderItemList";
import OrderActionButtons from "@/components/orders/OrderActionButtons";
import OrderStatusBadge from "@/components/orders/OrderStatusBadge";
import { DeliveryRouteMap } from "@/components/orders/DeliveryRouteMap";
import RequestedDeliveryLine from "@/components/orders/RequestedDeliveryLine";
import LoadError from "@/components/LoadError";
import CourierAdminActions from "@/components/orders/courier/CourierAdminActions";
import CourierSummary from "@/components/orders/courier/CourierSummary";
import { courierChargePending } from "@/lib/courier";
import type { Order } from "@/types";
import styles from "./page.module.css";

export default function AdminOrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const t = useTranslations("Admin.orderDetail");
  const tc = useTranslations("Admin.common");
  const tp = useTranslations("Shared.paymentStatus");
  const tpm = useTranslations("Order.payment.method");
  const tcs = useTranslations("Admin.orderDetail.courier");
  const tco = useTranslations("Order.courier");
  const { id } = use(params);
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

  // Courier orders (spec 2026-10-02): the charge is quoted after the order.
  const isCourier = order.delivery_mode === "courier";
  const pendingCharge = courierChargePending(order);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>{t("title", { id: order.id })}</h1>
        <OrderStatusBadge status={order.status} deliveryMode={order.delivery_mode} />
      </div>
      <p className={styles.subtitle}>
        {order.store_name} <span className={styles.serviceChip}>· {order.service_name}</span>
        {order.customer_name && ` · ${order.customer_name}`}
      </p>
      <RequestedDeliveryLine order={order} className={styles.subtitle} />

      <section className={styles.section}>
        <OrderTimeline status={order.status} deliveryMode={order.delivery_mode} />
      </section>

      {isCourier && <CourierSummary order={order} viewer="admin" />}

      <DeliveryOtpPanel
        order={order}
        onChange={setOrder}
        namespace="Admin.orderDetail"
      />

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{t("items")}</h2>
        <OrderItemList items={order.items} />
        <div className={styles.totals}>
          <div><span>{t("subtotal")}</span><span>₹{order.subtotal.toFixed(2)}</span></div>
          <div>
            <span>{isCourier ? tcs("charge") : t("delivery")}</span>
            <span>{pendingCharge ? tcs("toBeQuoted") : `₹${order.delivery_fee.toFixed(2)}`}</span>
          </div>
          <div><span>{t("tax")}</span><span>₹{order.tax.toFixed(2)}</span></div>
          <div className={styles.grand}>
            <span>{t("total")}</span>
            <span>
              {pendingCharge
                ? tcs("totalPlusCourier", { amount: order.total.toFixed(2) })
                : `₹${order.total.toFixed(2)}`}
            </span>
          </div>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{t("payment")}</h2>
        <p>
          {isCourier && order.payment.method === "net_banking"
            ? tco("methodBank")
            : tpm(order.payment.method)}{" "}
          · {order.courier?.refund_due ? tp("refund_due") : tp(order.payment.status)}
        </p>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{isCourier ? tcs("shipTo") : t("deliveryTo")}</h2>
        <p>{order.delivery_address_snapshot}</p>
        {/* No route for courier: meaningless at that distance (spec §8.2). */}
        {!isCourier &&
          order.store_latitude != null &&
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
                label: order.customer_name ?? t("customer"),
              }}
            />
          )}
      </section>

      <section className={styles.section}>
        {isCourier ? (
          <CourierAdminActions order={order} onChange={setOrder} />
        ) : (
          <OrderActionButtons order={order} role="admin" onChange={setOrder} />
        )}
      </section>
    </div>
  );
}
