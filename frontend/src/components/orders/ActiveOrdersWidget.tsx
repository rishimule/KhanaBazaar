"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
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
  const t = useTranslations("Order.active");
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
          if (!cancelled) setError(e?.detail ?? t("errLoad"));
        });
    tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [token, limit, t]);

  return (
    <section className={styles.widget}>
      <div className={styles.header}>
        <h2 className={styles.title}>{t("title")}</h2>
        <Link href={VIEW_ALL_HREF[role]} className={styles.viewAll}>
          {t("viewAll")}
        </Link>
      </div>
      {error && <div className={styles.error}>{error}</div>}
      {orders.length === 0 ? (
        <div className={styles.empty}>{t("empty")}</div>
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
