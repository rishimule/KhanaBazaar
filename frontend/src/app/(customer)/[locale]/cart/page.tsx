"use client";

import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/lib/AuthContext";
import { useCart } from "@/lib/CartContext";
import styles from "./page.module.css";

export default function CartPage() {
  const { carts, removeItem, updateQty, clearStoreCart, getTotal } = useCart();
  const { dbUser } = useAuth();
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleClear = async (storeId: number) => {
    setErrorMsg(null);
    try {
      await clearStoreCart(storeId);
    } catch (err) {
      const detail =
        (err as { detail?: string })?.detail ??
        (err instanceof Error ? err.message : null);
      setErrorMsg(detail ?? "Could not clear cart. Please try again.");
    }
  };

  const handleRemove = async (storeId: number, productId: number) => {
    setErrorMsg(null);
    try {
      await removeItem(storeId, productId);
    } catch (err) {
      const detail =
        (err as { detail?: string })?.detail ??
        (err instanceof Error ? err.message : null);
      setErrorMsg(detail ?? "Could not remove item. Please try again.");
    }
  };

  const handleUpdateQty = async (
    storeId: number,
    productId: number,
    qty: number
  ) => {
    setErrorMsg(null);
    try {
      await updateQty(storeId, productId, qty);
    } catch (err) {
      const detail =
        (err as { detail?: string })?.detail ??
        (err instanceof Error ? err.message : null);
      setErrorMsg(detail ?? "Could not update quantity. Please try again.");
    }
  };

  if (carts.length === 0) {
    return (
      <div className={styles.page}>
        <div className={styles.pageInner}>
          <div className={styles.empty}>
            <div className={styles.emptyIcon}>🛒</div>
            <h1 className={styles.emptyTitle}>Your cart is empty</h1>
            <p className={styles.emptyText}>
              Looks like you haven&apos;t added anything yet. Browse nearby
              stores and start adding items!
            </p>
            <Link href="/stores" className="btn btn-primary" id="empty-cart-shop">
              Start Shopping
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const isCustomer = dbUser?.role === "customer";

  const renderCheckoutCta = (storeId: number, subtotal: number) => {
    if (!dbUser) {
      return (
        <Link href={`/login?next=/checkout/${storeId}`} className={styles.checkoutBtn}>
          Login to checkout
        </Link>
      );
    }
    if (!isCustomer) {
      return (
        <span className={styles.checkoutBtn} aria-disabled>
          Customer login required
        </span>
      );
    }
    return (
      <Link href={`/checkout/${storeId}`} className={styles.checkoutBtn}>
        Checkout · ₹{subtotal}
      </Link>
    );
  };

  return (
    <div className={styles.page}>
      <div className={styles.pageInner}>
        <div className={styles.header}>
          <h1 className={styles.title}>
            Your <span className={styles.titleAccent}>Cart</span>
          </h1>
          <p className={styles.subtitle}>
            {carts.length} store{carts.length > 1 ? "s" : ""} ·{" "}
            {carts.reduce(
              (sum, c) => sum + c.items.reduce((s, i) => s + i.quantity, 0),
              0
            )}{" "}
            items
          </p>
        </div>

        {errorMsg ? (
          <div role="alert" className={styles.errorBanner}>
            {errorMsg}
          </div>
        ) : null}

        {carts.map((cart) => {
          const subtotal = getTotal(cart);
          return (
            <div key={cart.store_id} className={styles.storeGroup}>
              <div className={styles.storeGroupHeader}>
                <div className={styles.storeGroupTitle}>
                  🏪{" "}
                  <Link
                    href={`/stores/${cart.store_id}`}
                    className={styles.storeGroupLink}
                  >
                    {cart.store_name}
                  </Link>
                </div>
                <button
                  className={styles.clearBtn}
                  onClick={() => handleClear(cart.store_id)}
                >
                  Clear all
                </button>
              </div>

              {cart.items.map((item) => (
                <div key={item.product_id} className={styles.cartItem}>
                  <div className={styles.itemEmoji}>📦</div>

                  <div className={styles.itemInfo}>
                    <div className={styles.itemName}>{item.product_name}</div>
                    <div className={styles.itemPrice}>₹{item.price} each</div>
                  </div>

                  <div className={styles.qtyControls}>
                    <button
                      className={styles.qtyBtn}
                      onClick={() =>
                        item.quantity <= 1
                          ? handleRemove(cart.store_id, item.product_id)
                          : handleUpdateQty(
                              cart.store_id,
                              item.product_id,
                              item.quantity - 1
                            )
                      }
                    >
                      −
                    </button>
                    <span className={styles.qtyValue}>{item.quantity}</span>
                    <button
                      className={styles.qtyBtn}
                      onClick={() =>
                        handleUpdateQty(
                          cart.store_id,
                          item.product_id,
                          item.quantity + 1
                        )
                      }
                    >
                      +
                    </button>
                  </div>

                  <div className={styles.itemTotal}>
                    ₹{item.price * item.quantity}
                  </div>

                  <button
                    className={styles.removeBtn}
                    onClick={() => handleRemove(cart.store_id, item.product_id)}
                    aria-label={`Remove ${item.product_name}`}
                  >
                    ✕
                  </button>
                </div>
              ))}

              <div className={styles.storeFooter}>
                <span className={styles.storeSubtotalValue}>
                  Subtotal: ₹{subtotal}
                </span>
                {renderCheckoutCta(cart.store_id, subtotal)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
