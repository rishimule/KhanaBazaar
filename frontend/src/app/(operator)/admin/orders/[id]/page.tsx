"use client";

import { use, useEffect, useState } from "react";
import { getOrder } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import OrderTimeline from "@/components/orders/OrderTimeline";
import OrderItemList from "@/components/orders/OrderItemList";
import OrderActionButtons from "@/components/orders/OrderActionButtons";
import OrderStatusBadge from "@/components/orders/OrderStatusBadge";
import type { Order } from "@/types";
import styles from "./page.module.css";

export default function AdminOrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { token } = useAuth();
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    getOrder(token, Number(id))
      .then(setOrder)
      .catch((e: { detail?: string }) => setError(e?.detail ?? "Could not load order."));
  }, [token, id]);

  if (error) return <div className={styles.error}>{error}</div>;
  if (!order) return <div className={styles.loading}>Loading…</div>;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Order #{order.id}</h1>
        <OrderStatusBadge status={order.status} />
      </div>
      <p className={styles.subtitle}>
        {order.store_name}
        {order.customer_name && ` · ${order.customer_name}`}
      </p>

      <section className={styles.section}>
        <OrderTimeline status={order.status} />
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Items</h2>
        <OrderItemList items={order.items} />
        <div className={styles.totals}>
          <div><span>Subtotal</span><span>₹{order.subtotal.toFixed(2)}</span></div>
          <div><span>Delivery</span><span>₹{order.delivery_fee.toFixed(2)}</span></div>
          <div><span>Tax</span><span>₹{order.tax.toFixed(2)}</span></div>
          <div className={styles.grand}><span>Total</span><span>₹{order.total.toFixed(2)}</span></div>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Payment</h2>
        <p>{order.payment.method.toUpperCase()} · {order.payment.status}</p>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Delivery to</h2>
        <p>{order.delivery_address_snapshot}</p>
      </section>

      <section className={styles.section}>
        <OrderActionButtons order={order} role="admin" onChange={setOrder} />
      </section>
    </div>
  );
}
