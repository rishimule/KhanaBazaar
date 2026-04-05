"use client";

import Link from "next/link";
import { useCart } from "@/lib/CartContext";
import styles from "./page.module.css";

export default function CartPage() {
  const { carts, removeItem, updateQty, clearStoreCart, getTotal, grandTotal } =
    useCart();

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

  return (
    <div className={styles.page}>
      <div className={styles.pageInner}>
        {/* Header */}
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

        {/* Cart groups by store */}
        {carts.map((cart) => (
          <div key={cart.store_id} className={styles.storeGroup}>
            {/* Store header */}
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
                onClick={() => clearStoreCart(cart.store_id)}
              >
                Clear all
              </button>
            </div>

            {/* Items */}
            {cart.items.map((item) => (
              <div key={item.product_id} className={styles.cartItem}>
                <div className={styles.itemEmoji}>📦</div>

                <div className={styles.itemInfo}>
                  <div className={styles.itemName}>{item.product_name}</div>
                  <div className={styles.itemPrice}>₹{item.price} each</div>
                </div>

                {/* Quantity */}
                <div className={styles.qtyControls}>
                  <button
                    className={styles.qtyBtn}
                    onClick={() =>
                      item.quantity <= 1
                        ? removeItem(cart.store_id, item.product_id)
                        : updateQty(
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
                      updateQty(
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
                  onClick={() => removeItem(cart.store_id, item.product_id)}
                  aria-label={`Remove ${item.product_name}`}
                >
                  ✕
                </button>
              </div>
            ))}

            {/* Store subtotal */}
            <div className={styles.storeSubtotal}>
              <span>Subtotal:</span>
              <span className={styles.storeSubtotalValue}>
                ₹{getTotal(cart)}
              </span>
            </div>
          </div>
        ))}

        {/* Grand total */}
        <div className={styles.totalBar}>
          <span className={styles.totalLabel}>Grand Total</span>
          <div className={styles.totalRight}>
            <span className={styles.totalValue}>₹{grandTotal}</span>
            <button className={styles.checkoutBtn} disabled>
              Proceed to Checkout
              <span className={styles.checkoutTooltip}>
                Checkout flow and payment integration coming in a future phase 🚀
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
