// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import type { OrderItem } from "@/types";
import styles from "./OrderItemList.module.css";

export default function OrderItemList({ items }: { items: OrderItem[] }) {
  return (
    <ul className={styles.list}>
      {items.map((item) => (
        <li key={item.id} className={styles.row}>
          <span className={styles.name}>{item.product_name_snapshot}</span>
          <span className={styles.qty}>× {item.quantity}</span>
          <span className={styles.unit}>₹{item.unit_price_snapshot.toFixed(2)}</span>
          <span className={styles.total}>₹{item.line_total.toFixed(2)}</span>
        </li>
      ))}
    </ul>
  );
}
