"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { use, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { getOrder } from "@/lib/orders";
import { formatDeliveryEta } from "@/lib/deliveryEta";
import { useAuth } from "@/lib/AuthContext";
import { apiErrorCode, apiErrorKey } from "@/lib/errors";
import OrderTimeline from "@/components/orders/OrderTimeline";
import DeliveryOtpPanel from "@/components/orders/DeliveryOtpPanel";
import LocalPayPanel from "@/components/orders/LocalPayPanel";
import ReturnEntryPoint from "@/components/returns/ReturnEntryPoint";
import OrderItemList from "@/components/orders/OrderItemList";
import OrderActionButtons from "@/components/orders/OrderActionButtons";
import ReorderButton from "@/components/orders/ReorderButton";
import OrderStatusBadge from "@/components/orders/OrderStatusBadge";
import PaymentStatusBadge from "@/components/orders/PaymentStatusBadge";
import { DeliveryRouteMap } from "@/components/orders/DeliveryRouteMap";
import RequestedDeliveryLine from "@/components/orders/RequestedDeliveryLine";
import Skeleton from "@/components/Skeleton";
import CourierCustomerActions from "@/components/orders/courier/CourierCustomerActions";
import CourierPayPanel from "@/components/orders/courier/CourierPayPanel";
import CourierQuoteCard from "@/components/orders/courier/CourierQuoteCard";
import CourierSummary from "@/components/orders/courier/CourierSummary";
import { courierChargePending, latestQuote } from "@/lib/courier";
import type { Order } from "@/types";
import styles from "./page.module.css";

export default function CustomerOrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { token } = useAuth();
  const t = useTranslations("Account.orderDetail");
  const tErr = useTranslations("Errors");
  const tpm = useTranslations("Order.payment.method");
  const tco = useTranslations("Order.courier");
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
          // apiErrorCode() always returns a string or null. The old cast
          // claimed `string` while the backend can send an object, which then
          // rendered as a JSX child and crashed the page (audit BLOCKER #32).
          setError(apiErrorCode(e) ?? t("loadError"));
        }
      });
  }, [token, id, t, tErr]);

  if (error) return <div className={styles.error}>{error}</div>;
  if (!order)
    return (
      <div className={styles.page} aria-busy="true" style={{ display: "grid", gap: "12px" }}>
        <Skeleton height={28} width="55%" />
        <Skeleton height={16} width="35%" />
        <Skeleton height={140} radius="var(--radius-card)" />
        <Skeleton height={220} radius="var(--radius-card)" />
      </div>
    );

  // Courier orders (spec 2026-10-02): quote → accept → pay → ship, no OTP.
  const isCourier = order.delivery_mode === "courier";

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>{t("title", { id: order.id })}</h1>
        <OrderStatusBadge
          status={order.status}
          deliveryMode={order.delivery_mode}
          audience="customer"
        />
      </div>
      <p className={styles.subtitle}>
        {order.store_name} <span className={styles.serviceChip}>· {order.service_name}</span>
      </p>
      {!isCourier &&
        order.delivery_eta_min_minutes != null &&
        order.delivery_eta_max_minutes != null && (
        <p className={styles.subtitle}>
          {t("estimatedDelivery")}:{" "}
          {formatDeliveryEta(order.delivery_eta_min_minutes, order.delivery_eta_max_minutes)}
        </p>
      )}
      <RequestedDeliveryLine order={order} className={styles.subtitle} />

      <section className={styles.section}>
        <OrderTimeline status={order.status} deliveryMode={order.delivery_mode} />
      </section>

      {isCourier && (
        <>
          <CourierQuoteCard order={order} onChange={setOrder} />
          <CourierPayPanel order={order} onChange={setOrder} />
          <CourierSummary order={order} viewer="customer" />
        </>
      )}

      <LocalPayPanel order={order} onChange={setOrder} />

      <DeliveryOtpPanel order={order} onChange={setOrder} />

      {isCourier ? (
        order.status === "delivered" && (
          <p className={styles.subtitle}>{t("courierNoReturns")}</p>
        )
      ) : (
        <ReturnEntryPoint order={order} />
      )}

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{t("items")}</h2>
        <OrderItemList items={order.items} />
        <div className={styles.totals}>
          <div><span>{t("subtotal")}</span><span>{t("amount", { amount: order.subtotal.toFixed(2) })}</span></div>
          <div>
            <span>{isCourier ? t("courierCharge") : t("delivery")}</span>
            <span>
              {courierChargePending(order)
                ? order.status === "quoted" && latestQuote(order)
                  ? t("courierQuotedCharge", { amount: latestQuote(order)!.courier_fee.toFixed(2) })
                  : t("courierToBeQuoted")
                : t("amount", { amount: order.delivery_fee.toFixed(2) })}
            </span>
          </div>
          <div><span>{t("tax")}</span><span>{t("amount", { amount: order.tax.toFixed(2) })}</span></div>
          <div className={styles.grand}>
            <span>{t("total")}</span>
            <span>
              {courierChargePending(order)
                ? t("amountPlusCourier", { amount: order.total.toFixed(2) })
                : t("amount", { amount: order.total.toFixed(2) })}
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
          ·{" "}
          <PaymentStatusBadge status={order.payment.status} refundDue={order.courier?.refund_due} />
        </p>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>
          {order.delivery_mode === "pickup"
            ? t("pickupLocation")
            : isCourier
              ? t("courierShipTo")
              : t("deliveryTo")}
        </h2>
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
                label: "Your address",
              }}
            />
          )}
      </section>

      <section className={styles.section}>
        <div className={styles.actionRow}>
          <ReorderButton orderId={order.id} className={styles.reorderBtn} />
          {isCourier ? (
            <CourierCustomerActions order={order} onChange={setOrder} />
          ) : (
            <OrderActionButtons order={order} role="customer" onChange={setOrder} />
          )}
        </div>
      </section>
    </div>
  );
}
