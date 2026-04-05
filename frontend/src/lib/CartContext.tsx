"use client";

/**
 * Khana Bazaar — Cart Context
 *
 * React Context providing reactive cart state to all components.
 * Wraps the localStorage cart module with React state management.
 * Uses lazy initialization to hydrate from localStorage without useEffect.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useState,
} from "react";

import { Cart, CartItem } from "@/types";
import * as cartLib from "@/lib/cart";

interface CartContextValue {
  carts: Cart[];
  cartCount: number;
  addItem: (storeId: number, storeName: string, item: CartItem) => void;
  removeItem: (storeId: number, productId: number) => void;
  updateQty: (storeId: number, productId: number, qty: number) => void;
  clearStoreCart: (storeId: number) => void;
  clearAll: () => void;
  getTotal: (cart: Cart) => number;
  grandTotal: number;
}

const CartContext = createContext<CartContextValue | null>(null);

/** Safely read carts from localStorage (returns [] during SSR). */
function getInitialCarts(): Cart[] {
  if (typeof window === "undefined") return [];
  return cartLib.getAllCarts();
}

function computeCount(carts: Cart[]): number {
  return carts.reduce(
    (sum, c) => sum + c.items.reduce((s, i) => s + i.quantity, 0),
    0
  );
}

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [carts, setCarts] = useState<Cart[]>(getInitialCarts);
  const [cartCount, setCartCount] = useState(() => computeCount(getInitialCarts()));

  const refresh = useCallback((updated: Cart[]) => {
    setCarts(updated);
    setCartCount(computeCount(updated));
  }, []);

  const addItem = useCallback(
    (storeId: number, storeName: string, item: CartItem) => {
      refresh(cartLib.addToCart(storeId, storeName, item));
    },
    [refresh]
  );

  const removeItem = useCallback(
    (storeId: number, productId: number) => {
      refresh(cartLib.removeFromCart(storeId, productId));
    },
    [refresh]
  );

  const updateQty = useCallback(
    (storeId: number, productId: number, qty: number) => {
      refresh(cartLib.updateQuantity(storeId, productId, qty));
    },
    [refresh]
  );

  const clearStoreCart = useCallback(
    (storeId: number) => {
      refresh(cartLib.clearCart(storeId));
    },
    [refresh]
  );

  const clearAll = useCallback(() => {
    refresh(cartLib.clearAllCarts());
  }, [refresh]);

  const getTotal = useCallback((cart: Cart) => cartLib.getCartTotal(cart), []);

  const grandTotal = carts.reduce((sum, c) => sum + cartLib.getCartTotal(c), 0);

  return (
    <CartContext.Provider
      value={{
        carts,
        cartCount,
        addItem,
        removeItem,
        updateQty,
        clearStoreCart,
        clearAll,
        getTotal,
        grandTotal,
      }}
    >
      {children}
    </CartContext.Provider>
  );
}

export function useCart(): CartContextValue {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used within <CartProvider>");
  return ctx;
}
