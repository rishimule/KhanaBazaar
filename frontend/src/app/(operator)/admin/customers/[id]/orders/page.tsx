"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import OrderStatusBadge from "@/components/orders/OrderStatusBadge";
import { useAuth } from "@/lib/AuthContext";
import { fetchCustomerOrders } from "@/lib/adminCustomers";
import type { AdminCustomerOrder } from "@/types";
import styles from "../tabs.module.css";

export default function CustomerOrdersTab({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const t = useTranslations("Admin.customers");
  const tc = useTranslations("Admin.common");
  const { token } = useAuth();
  const [orders, setOrders] = useState<AdminCustomerOrder[] | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setOrders(await fetchCustomerOrders(Number(id), token));
    } catch {
      setError(true);
    }
  }, [id, token]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial load sets state inside async callbacks
    load();
  }, [load]);

  if (error) return <div className={styles.errorBox}>{t("orders.loadError")}</div>;
  if (!orders) return <div className={styles.state}>{tc("loading")}</div>;

  return (
    <div>
      <h2 className={styles.heading}>
        {t("orders.heading", { n: orders.length })}
      </h2>
      {orders.length === 0 ? (
        <div className={styles.empty}>{t("orders.empty")}</div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{t("orders.col.order")}</th>
                <th>{t("orders.col.service")}</th>
                <th>{t("orders.col.status")}</th>
                <th>{t("orders.col.total")}</th>
                <th>{t("orders.col.placed")}</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id}>
                  <td>
                    <Link href={`/admin/orders/${o.id}`}>#{o.id}</Link>
                  </td>
                  <td>{o.service_name_snapshot ?? "—"}</td>
                  <td>
                    <OrderStatusBadge status={o.status} />
                  </td>
                  <td>₹{o.total.toFixed(2)}</td>
                  <td>{new Date(o.placed_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
