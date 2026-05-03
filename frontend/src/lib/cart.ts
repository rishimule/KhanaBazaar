/**
 * Cart shared helpers and re-exports.
 *
 * Pure helpers used by both guest (localCart) and authenticated (remoteCart) flows.
 */
import type { Cart } from "@/types";

export function getCartTotal(cart: Cart): number {
  return cart.items.reduce((sum, i) => i.price * i.quantity + sum, 0);
}

export function getGrandTotal(carts: Cart[]): number {
  return carts.reduce((sum, c) => sum + getCartTotal(c), 0);
}

export function getCartCount(carts: Cart[]): number {
  return carts.reduce((sum, c) => sum + c.items.reduce((s, i) => s + i.quantity, 0), 0);
}

// Re-export guest API for callers still using it directly.
export * as localCart from "@/lib/localCart";
