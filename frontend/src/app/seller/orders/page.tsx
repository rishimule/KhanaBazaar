"use client";

import { useEffect, useState } from "react";
import { listOrders } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import OrderCard from "@/components/orders/OrderCard";
import type { Order } from "@/types";
import styles from "./page.module.css";

type Tab = "active" | "history";

export default function SellerOrdersPage() {
  const { token } = useAuth();
  const [tab, setTab] = useState<Tab>("active");
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    listOrders(token, tab)
      .then(setOrders)
      .finally(() => setLoading(false));
  }, [token, tab]);

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Store orders</h1>
      <div className={styles.tabs}>
        <button
          className={tab === "active" ? styles.tabActive : styles.tab}
          onClick={() => setTab("active")}
        >Active</button>
        <button
          className={tab === "history" ? styles.tabActive : styles.tab}
          onClick={() => setTab("history")}
        >History</button>
      </div>
      {loading ? (
        <div className={styles.empty}>Loading…</div>
      ) : orders.length === 0 ? (
        <div className={styles.empty}>No {tab} orders.</div>
      ) : (
        <div className={styles.grid}>
          {orders.map((o) => (
            <OrderCard key={o.id} order={o} role="seller" />
          ))}
        </div>
      )}
    </div>
  );
}
