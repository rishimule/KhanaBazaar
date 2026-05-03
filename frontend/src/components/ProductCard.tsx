"use client";

import { useCart } from "@/lib/CartContext";
import { useAuth } from "@/lib/AuthContext";
import { InventoryWithProduct } from "@/types";
import styles from "./ProductCard.module.css";

interface Props {
  item: InventoryWithProduct;
  storeId: number;
  storeName: string;
}

/** Category → emoji mapping for image placeholders. */
const CATEGORY_EMOJI: Record<number, string> = {
  1: "🥬",  // Fruits & Vegetables
  2: "🥛",  // Dairy & Bakery
  3: "🌾",  // Staples & Grains
  4: "🍪",  // Snacks & Beverages
};

export default function ProductCard({ item, storeId, storeName }: Props) {
  const { carts, addItem, removeItem, updateQty } = useCart();
  const { dbUser } = useAuth();
  const { product, price, stock } = item;
  
  const role = dbUser?.role;

  // Find current qty in cart
  const cart = carts.find((c) => c.store_id === storeId);
  const cartItem = cart?.items.find((i) => i.product_id === product.id);
  const qty = cartItem?.quantity ?? 0;

  const stockLabel =
    stock === 0 ? "Out of stock" : stock <= 5 ? `Only ${stock} left` : "In stock";
  const stockClass =
    stock === 0 ? styles.outOfStock : stock <= 5 ? styles.lowStock : styles.inStock;

  const handleAdd = () => {
    addItem(storeId, storeName, {
      product_id: product.id,
      inventory_id: item.id,
      product_name: product.name,
      quantity: 1,
      price,
      image_url: product.image_url,
    });
  };

  return (
    <div className={styles.card}>
      {/* Image */}
      <div className={styles.imageWrap}>
        <span className={styles.imagePlaceholder}>
          {CATEGORY_EMOJI[product.category_id] ?? "📦"}
        </span>
      </div>

      {/* Content */}
      <div className={styles.content}>
        <h3 className={styles.name}>{product.name}</h3>
        <p className={styles.description}>{product.description}</p>

        <div className={styles.priceRow}>
          <span className={styles.price}>
            <span className={styles.priceCurrency}>₹</span>
            {price}
          </span>
          <span className={`${styles.stockBadge} ${stockClass}`}>
            {stockLabel}
          </span>
        </div>
      </div>

      {/* Actions */}
      {role === "customer" && (
        <div className={styles.actions}>
        {qty === 0 ? (
          <button
            className={styles.addBtn}
            onClick={handleAdd}
            disabled={stock === 0}
          >
            {stock === 0 ? "Out of Stock" : "Add to Cart"}
          </button>
        ) : (
          <div className={styles.qtyControls}>
            <button
              className={styles.qtyBtn}
              onClick={() =>
                qty <= 1
                  ? removeItem(storeId, product.id)
                  : updateQty(storeId, product.id, qty - 1)
              }
            >
              −
            </button>
            <span className={styles.qtyValue}>{qty}</span>
            <button
              className={styles.qtyBtn}
              onClick={() => updateQty(storeId, product.id, qty + 1)}
              disabled={qty >= stock}
            >
              +
            </button>
          </div>
        )}
      </div>
      )}
    </div>
  );
}
