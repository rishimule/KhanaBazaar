"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listOrders } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import OrderCard from "./OrderCard";
import type { Order, UserRole } from "@/types";
import styles from "./ActiveOrdersWidget.module.css";

interface Props {
  role: UserRole;
  limit?: number;
}

const VIEW_ALL_HREF: Record<UserRole, string> = {
  customer: "/account/orders",
  seller: "/seller/orders",
  admin: "/admin/orders",
};

const POLL_MS = 15_000;

export default function ActiveOrdersWidget({ role, limit = 5 }: Props) {
  const { token } = useAuth();
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    const tick = () =>
      listOrders(token, "active")
        .then((data) => {
          if (!cancelled) {
            setOrders(data.slice(0, limit));
            setError(null);
          }
        })
        .catch((e: { detail?: string }) => {
          if (!cancelled) setError(e?.detail ?? "Could not load orders.");
        });
    tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [token, limit]);

  return (
    <section className={styles.widget}>
      <div className={styles.header}>
        <h2 className={styles.title}>Active orders</h2>
        <Link href={VIEW_ALL_HREF[role]} className={styles.viewAll}>
          View all
        </Link>
      </div>
      {error && <div className={styles.error}>{error}</div>}
      {orders.length === 0 ? (
        <div className={styles.empty}>No active orders.</div>
      ) : (
        <div className={styles.grid}>
          {orders.map((o) => (
            <OrderCard key={o.id} order={o} role={role} />
          ))}
        </div>
      )}
    </section>
  );
}
