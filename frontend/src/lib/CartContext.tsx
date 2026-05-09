"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useAuth } from "@/lib/AuthContext";
import * as localCart from "@/lib/localCart";
import * as remoteCart from "@/lib/remoteCart";
import { getCartCount, getCartTotal, getGrandTotal } from "@/lib/cart";
import type { Cart, CartItem } from "@/types";

interface CartContextValue {
  carts: Cart[];
  cartCount: number;
  loading: boolean;
  addItem: (storeId: number, storeName: string, item: CartItem) => Promise<void>;
  removeItem: (storeId: number, productId: number) => Promise<void>;
  updateQty: (storeId: number, productId: number, qty: number) => Promise<void>;
  clearStoreCart: (storeId: number) => Promise<void>;
  getTotal: (cart: Cart) => number;
  grandTotal: number;
  refresh: () => Promise<void>;
  lastSyncDropped: number;
  clearSyncDropped: () => void;
}

const CartContext = createContext<CartContextValue | null>(null);

function findRemoteItemId(carts: Cart[], storeId: number, productId: number): number | undefined {
  const cart = carts.find((c) => c.store_id === storeId);
  return cart?.items.find((i) => i.product_id === productId)?.id;
}

export function CartProvider({ children }: { children: React.ReactNode }) {
  const { dbUser, token, loading: authLoading } = useAuth();
  const [carts, setCarts] = useState<Cart[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [lastSyncDropped, setLastSyncDropped] = useState<number>(0);
  const lastSyncedUserId = useRef<number | null>(null);

  // Reset the sync sentinel whenever the active user disappears (logout) or
  // changes (account swap in same tab) so the next login re-syncs against
  // its own localStorage rather than the previous user's stale state.
  useEffect(() => {
    if (!dbUser) {
      lastSyncedUserId.current = null;
    }
  }, [dbUser]);

  const refreshLocal = useCallback(() => {
    setCarts(localCart.getAllCarts());
  }, []);

  const refreshRemote = useCallback(async () => {
    if (!token) return;
    const fresh = await remoteCart.listCarts(token);
    setCarts(fresh);
  }, [token]);

  const isCustomer = !!dbUser && dbUser.role === "customer" && !!token;

  const refresh = useCallback(async () => {
    if (isCustomer) {
      await refreshRemote();
    } else {
      refreshLocal();
    }
  }, [isCustomer, refreshRemote, refreshLocal]);

  // Initial load + auth transitions.
  useEffect(() => {
    if (authLoading) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      if (!dbUser || dbUser.role !== "customer" || !token) {
        if (!cancelled) {
          refreshLocal();
          setLoading(false);
        }
        return;
      }
      try {
        if (lastSyncedUserId.current !== dbUser.id) {
          const local = localCart.getAllCarts();
          if (local.length > 0) {
            const payload = local.map((c) => ({
              store_id: c.store_id,
              items: c.items
                .filter((i) => typeof i.inventory_id === "number")
                .map((i) => ({ inventory_id: i.inventory_id, quantity: i.quantity })),
            }));
            const result = await remoteCart.syncCarts(token, payload);
            if (!cancelled) {
              setCarts(result.carts);
              setLastSyncDropped(result.dropped.length);
            }
            localCart.clearAllCarts();
          } else {
            await refreshRemote();
          }
          lastSyncedUserId.current = dbUser.id;
        } else {
          await refreshRemote();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authLoading, dbUser, token, refreshLocal, refreshRemote]);

  const addItem = useCallback(
    async (storeId: number, storeName: string, item: CartItem) => {
      if (!isCustomer) {
        const updated = localCart.addToCart(storeId, storeName, item);
        setCarts(updated);
        return;
      }
      const previous = carts;
      setCarts((prev) => {
        const next = prev.map((c) => ({ ...c, items: [...c.items] }));
        let cart = next.find((c) => c.store_id === storeId);
        if (!cart) {
          cart = { store_id: storeId, store_name: storeName, items: [] };
          next.push(cart);
        }
        const existing = cart.items.find((i) => i.product_id === item.product_id);
        if (existing) {
          existing.quantity += item.quantity;
        } else {
          cart.items.push({ ...item });
        }
        return next;
      });
      try {
        await remoteCart.addItem(token!, storeId, item.inventory_id, item.quantity);
        await refreshRemote();
      } catch (err) {
        setCarts(previous);
        throw err;
      }
    },
    [carts, isCustomer, token, refreshRemote]
  );

  const removeItem = useCallback(
    async (storeId: number, productId: number) => {
      if (!isCustomer) {
        setCarts(localCart.removeFromCart(storeId, productId));
        return;
      }
      const previous = carts;
      const itemId = findRemoteItemId(carts, storeId, productId);
      setCarts((prev) =>
        prev
          .map((c) =>
            c.store_id === storeId
              ? { ...c, items: c.items.filter((i) => i.product_id !== productId) }
              : c
          )
          .filter((c) => c.items.length > 0)
      );
      if (!itemId) return;
      try {
        await remoteCart.removeItem(token!, itemId);
        await refreshRemote();
      } catch (err) {
        setCarts(previous);
        throw err;
      }
    },
    [carts, isCustomer, token, refreshRemote]
  );

  const updateQty = useCallback(
    async (storeId: number, productId: number, qty: number) => {
      if (qty <= 0) {
        await removeItem(storeId, productId);
        return;
      }
      if (!isCustomer) {
        setCarts(localCart.updateQuantity(storeId, productId, qty));
        return;
      }
      const previous = carts;
      const itemId = findRemoteItemId(carts, storeId, productId);
      setCarts((prev) =>
        prev.map((c) =>
          c.store_id === storeId
            ? {
                ...c,
                items: c.items.map((i) =>
                  i.product_id === productId ? { ...i, quantity: qty } : i
                ),
              }
            : c
        )
      );
      if (!itemId) return;
      try {
        await remoteCart.updateItemQty(token!, itemId, qty);
        await refreshRemote();
      } catch (err) {
        setCarts(previous);
        throw err;
      }
    },
    [carts, isCustomer, token, refreshRemote, removeItem]
  );

  const clearStoreCart = useCallback(
    async (storeId: number) => {
      if (!isCustomer) {
        setCarts(localCart.clearCart(storeId));
        return;
      }
      const previous = carts;
      setCarts((prev) => prev.filter((c) => c.store_id !== storeId));
      try {
        await remoteCart.clearStoreCart(token!, storeId);
        await refreshRemote();
      } catch (err) {
        setCarts(previous);
        throw err;
      }
    },
    [carts, isCustomer, token, refreshRemote]
  );

  const cartCount = useMemo(() => getCartCount(carts), [carts]);
  const grandTotal = useMemo(() => getGrandTotal(carts), [carts]);

  const clearSyncDropped = useCallback(() => {
    setLastSyncDropped(0);
  }, []);

  const value: CartContextValue = {
    carts,
    cartCount,
    loading,
    addItem,
    removeItem,
    updateQty,
    clearStoreCart,
    getTotal: getCartTotal,
    grandTotal,
    refresh,
    lastSyncDropped,
    clearSyncDropped,
  };

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartContextValue {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used inside a CartProvider");
  return ctx;
}
