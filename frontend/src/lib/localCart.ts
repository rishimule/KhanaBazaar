// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Khana Bazaar — Guest Cart (localStorage adapter).
 *
 * Manages shopping carts in localStorage using a guest session_id pattern.
 * Each store has its own cart. Carts persist across page reloads.
 */

import { Cart, CartItem } from "@/types";

const CARTS_KEY = "kb_carts";
const SESSION_KEY = "kb_session_id";

/** Generate or retrieve a persistent guest session ID. */
export function getSessionId(): string {
  if (typeof window === "undefined") return "";
  let sid = localStorage.getItem(SESSION_KEY);
  if (!sid) {
    sid = crypto.randomUUID();
    localStorage.setItem(SESSION_KEY, sid);
  }
  return sid;
}

/** Read all carts from localStorage. */
export function getAllCarts(): Cart[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(CARTS_KEY);
    return raw ? (JSON.parse(raw) as Cart[]) : [];
  } catch {
    return [];
  }
}

/** Persist carts to localStorage. */
function saveCarts(carts: Cart[]): void {
  localStorage.setItem(CARTS_KEY, JSON.stringify(carts));
}

/** Get a single store's cart, or null if it doesn't exist. */
export function getCart(storeId: number): Cart | null {
  return getAllCarts().find((c) => c.store_id === storeId) ?? null;
}

/** Add an item to a store's cart (or increment if already present). */
export function addToCart(
  storeId: number,
  storeName: string,
  item: CartItem
): Cart[] {
  const carts = getAllCarts();
  let cart = carts.find((c) => c.store_id === storeId);

  if (!cart) {
    cart = { store_id: storeId, store_name: storeName, items: [] };
    carts.push(cart);
  }

  const existing = cart.items.find((i) => i.product_id === item.product_id);
  if (existing) {
    existing.quantity += item.quantity;
  } else {
    cart.items.push({ ...item });
  }

  saveCarts(carts);
  return carts;
}

/** Remove a specific product from a store's cart. */
export function removeFromCart(storeId: number, productId: number): Cart[] {
  const carts = getAllCarts();
  const cart = carts.find((c) => c.store_id === storeId);
  if (cart) {
    cart.items = cart.items.filter((i) => i.product_id !== productId);
    if (cart.items.length === 0) {
      const idx = carts.indexOf(cart);
      carts.splice(idx, 1);
    }
  }
  saveCarts(carts);
  return carts;
}

/** Update the quantity of a specific product in a store's cart. */
export function updateQuantity(
  storeId: number,
  productId: number,
  quantity: number
): Cart[] {
  if (quantity <= 0) return removeFromCart(storeId, productId);

  const carts = getAllCarts();
  const cart = carts.find((c) => c.store_id === storeId);
  if (cart) {
    const item = cart.items.find((i) => i.product_id === productId);
    if (item) item.quantity = quantity;
  }
  saveCarts(carts);
  return carts;
}

/** Clear a specific store's cart. */
export function clearCart(storeId: number): Cart[] {
  const carts = getAllCarts().filter((c) => c.store_id !== storeId);
  saveCarts(carts);
  return carts;
}

/** Clear all carts. */
export function clearAllCarts(): Cart[] {
  saveCarts([]);
  return [];
}
