// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Khana Bazaar — Guest Cart (localStorage adapter).
 *
 * Each (store, service) pair has its own sub-basket. Carts persist across
 * page reloads. v2 storage key supersedes the legacy `kb_carts` key; the
 * legacy key is purged on first read so stale single-service carts cannot
 * accumulate indefinitely after the upgrade.
 */

import { Cart, CartItem } from "@/types";

const CARTS_KEY = "kb_carts_v2";
const LEGACY_CARTS_KEY = "kb_carts";
const SESSION_KEY = "kb_session_id";

let legacyPurged = false;

function purgeLegacyOnce(): void {
  if (legacyPurged || typeof window === "undefined") return;
  legacyPurged = true;
  localStorage.removeItem(LEGACY_CARTS_KEY);
}

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

/** Read all sub-baskets from localStorage. */
export function getAllCarts(): Cart[] {
  if (typeof window === "undefined") return [];
  purgeLegacyOnce();
  try {
    const raw = localStorage.getItem(CARTS_KEY);
    return raw ? (JSON.parse(raw) as Cart[]) : [];
  } catch {
    return [];
  }
}

function saveCarts(carts: Cart[]): void {
  localStorage.setItem(CARTS_KEY, JSON.stringify(carts));
}

function find(
  carts: Cart[],
  storeId: number,
  serviceId: number,
): Cart | undefined {
  return carts.find(
    (c) => c.store_id === storeId && c.service_id === serviceId,
  );
}

/** Get a single sub-basket, or null. */
export function getCart(storeId: number, serviceId: number): Cart | null {
  return find(getAllCarts(), storeId, serviceId) ?? null;
}

/** Add an item to a sub-basket (or increment if already present). */
export function addToCart(
  storeId: number,
  storeName: string,
  serviceId: number,
  serviceName: string,
  item: CartItem,
): Cart[] {
  const carts = getAllCarts();
  let cart = find(carts, storeId, serviceId);

  if (!cart) {
    cart = {
      store_id: storeId,
      store_name: storeName,
      service_id: serviceId,
      service_name: serviceName,
      items: [],
    };
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

/** Remove a specific product from a sub-basket. */
export function removeFromCart(
  storeId: number,
  serviceId: number,
  productId: number,
): Cart[] {
  const carts = getAllCarts();
  const cart = find(carts, storeId, serviceId);
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

/** Update the quantity of a specific product in a sub-basket. */
export function updateQuantity(
  storeId: number,
  serviceId: number,
  productId: number,
  quantity: number,
): Cart[] {
  if (quantity <= 0) {
    return removeFromCart(storeId, serviceId, productId);
  }

  const carts = getAllCarts();
  const cart = find(carts, storeId, serviceId);
  if (cart) {
    const item = cart.items.find((i) => i.product_id === productId);
    if (item) item.quantity = quantity;
  }
  saveCarts(carts);
  return carts;
}

/** Clear a specific sub-basket. */
export function clearCart(storeId: number, serviceId: number): Cart[] {
  const carts = getAllCarts().filter(
    (c) => !(c.store_id === storeId && c.service_id === serviceId),
  );
  saveCarts(carts);
  return carts;
}

/** Clear all sub-baskets. */
export function clearAllCarts(): Cart[] {
  saveCarts([]);
  return [];
}
