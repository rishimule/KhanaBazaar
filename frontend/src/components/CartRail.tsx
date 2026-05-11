"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useCart } from "@/lib/CartContext";
import { useAuth } from "@/lib/AuthContext";
import styles from "./CartRail.module.css";

function CartThumb({ url }: { url?: string }) {
  const [failed, setFailed] = useState(false);
  if (!url || failed) return <span aria-hidden>🛍️</span>;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={url} alt="" onError={() => setFailed(true)} />;
}

interface Props {
  storeId?: number;
  serviceId?: number;
}

export default function CartRail({ storeId, serviceId }: Props) {
  const { carts } = useCart();
  const { dbUser } = useAuth();
  const router = useRouter();

  const role = dbUser?.role;
  if (role && role !== "customer") return null;

  const cart =
    storeId != null && serviceId != null
      ? carts.find(
          (c) => c.store_id === storeId && c.service_id === serviceId,
        )
      : null;

  const items = cart?.items ?? [];
  const subtotal = items.reduce((s, i) => s + i.price * i.quantity, 0);
  const totalQty = items.reduce((n, i) => n + i.quantity, 0);

  const onCheckout = () => {
    const target =
      storeId != null && serviceId != null
        ? `/checkout/${storeId}/${serviceId}`
        : "/cart";
    // Guests can't place an order — send them to login first so they
    // return to the right checkout (or cart) after auth instead of
    // landing on a checkout page that only renders a login prompt.
    if (!dbUser) {
      router.push(`/login?next=${encodeURIComponent(target)}`);
      return;
    }
    router.push(target);
  };

  return (
    <aside className={styles.rail} aria-label="Cart preview">
      <h3 className={styles.h}>Your cart ({totalQty})</h3>
      {items.length === 0 ? (
        <div className={styles.empty}>
          <div className={styles.emptyGlyph}>🛒</div>
          <div className={styles.emptyMsg}>Your cart is empty</div>
          <Link href="/stores" className={styles.emptyLink}>
            Browse stores →
          </Link>
        </div>
      ) : (
        <>
          <div className={styles.list}>
            {items.map((i) => (
              <div key={i.product_id} className={styles.item}>
                <div className={styles.thumb}>
                  <CartThumb url={i.image_url} />
                </div>
                <div>
                  <div className={styles.name}>{i.product_name}</div>
                  <div className={styles.qty}>Qty {i.quantity}</div>
                </div>
                <div className={styles.lt}>₹{(i.price * i.quantity).toFixed(2)}</div>
              </div>
            ))}
          </div>
          <div className={styles.totals}>
            <div className={styles.sub}>
              <span>Subtotal</span>
              <span>₹{subtotal.toFixed(2)}</span>
            </div>
            <div className={styles.eta}>Estimated delivery: same-day in 2 hours</div>
            <button className={styles.checkout} onClick={onCheckout}>
              Check out
            </button>
          </div>
        </>
      )}
    </aside>
  );
}
