"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useAuth } from "@/lib/AuthContext";
import { ApiError, del, get, post } from "@/lib/api";
import type { FavoriteIdsResponse } from "@/types";

interface FavoritesContextValue {
  isFavorite: (productId: number) => boolean;
  toggle: (productId: number) => Promise<void>;
  count: number;
  loaded: boolean;
}

const FavoritesContext = createContext<FavoritesContextValue | null>(null);

export function FavoritesProvider({ children }: { children: React.ReactNode }) {
  const { dbUser, token } = useAuth();
  const [ids, setIds] = useState<Set<number>>(new Set());
  const [loaded, setLoaded] = useState(false);
  const inflight = useRef<Map<number, Promise<void>>>(new Map());

  useEffect(() => {
    if (dbUser?.role !== "customer" || !token) {
      setIds(new Set());
      setLoaded(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await get<FavoriteIdsResponse>(
          "/api/v1/favorites/ids",
          token,
        );
        if (!cancelled) {
          setIds(new Set(res.ids));
          setLoaded(true);
        }
      } catch (e) {
        if (!cancelled) {
          console.error("favorites: ids fetch failed", e);
          setLoaded(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [dbUser?.role, dbUser?.id, token]);

  const isFavorite = useCallback(
    (productId: number) => ids.has(productId),
    [ids],
  );

  const toggle = useCallback(
    async (productId: number): Promise<void> => {
      if (dbUser?.role !== "customer" || !token) return;
      const existing = inflight.current.get(productId);
      if (existing) return existing;

      const wasFav = ids.has(productId);
      setIds((prev) => {
        const next = new Set(prev);
        if (wasFav) next.delete(productId);
        else next.add(productId);
        return next;
      });

      const p = (async () => {
        try {
          if (wasFav) {
            await del(`/api/v1/favorites/${productId}`, token);
          } else {
            await post(`/api/v1/favorites/${productId}`, undefined, token);
          }
        } catch (e) {
          setIds((prev) => {
            const next = new Set(prev);
            if (wasFav) next.add(productId);
            else next.delete(productId);
            return next;
          });
          console.error("favorites: toggle failed", e);
          if (e instanceof ApiError) throw e;
        } finally {
          inflight.current.delete(productId);
        }
      })();
      inflight.current.set(productId, p);
      return p;
    },
    [dbUser?.role, token, ids],
  );

  const value = useMemo<FavoritesContextValue>(
    () => ({ isFavorite, toggle, count: ids.size, loaded }),
    [isFavorite, toggle, ids.size, loaded],
  );

  return (
    <FavoritesContext.Provider value={value}>
      {children}
    </FavoritesContext.Provider>
  );
}

export function useFavorites(): FavoritesContextValue {
  const ctx = useContext(FavoritesContext);
  if (!ctx) {
    throw new Error("useFavorites must be used within <FavoritesProvider>");
  }
  return ctx;
}
