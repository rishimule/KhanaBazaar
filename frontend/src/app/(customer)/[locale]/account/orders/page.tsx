"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { listOrders } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import OrderCard from "@/components/orders/OrderCard";
import type { Order } from "@/types";
import styles from "./page.module.css";

type Tab = "active" | "history";

export default function CustomerOrdersPage() {
  const { token } = useAuth();
  const t = useTranslations("Account.orders");
  const [tab, setTab] = useState<Tab>("active");
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const search = useSearchParams();
  const justPlaced = search.get("placed");

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    listOrders(token, tab)
      .then((data) => { if (!cancelled) setOrders(data); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [token, tab]);

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>{t("title")}</h1>
      {justPlaced && (
        <div className={styles.toast}>
          {t("placedToast", { count: Number(justPlaced) })}
        </div>
      )}
      <div className={styles.tabs}>
        <button
          className={tab === "active" ? styles.tabActive : styles.tab}
          onClick={() => setTab("active")}
        >{t("tabActive")}</button>
        <button
          className={tab === "history" ? styles.tabActive : styles.tab}
          onClick={() => setTab("history")}
        >{t("tabHistory")}</button>
      </div>
      {loading ? (
        <div className={styles.empty}>{t("loading")}</div>
      ) : orders.length === 0 ? (
        <div className={styles.empty}>
          {tab === "active" ? t("emptyActive") : t("emptyHistory")}
        </div>
      ) : (
        <div className={styles.grid}>
          {orders.map((o) => (
            <OrderCard key={o.id} order={o} role="customer" />
          ))}
        </div>
      )}
    </div>
  );
}
