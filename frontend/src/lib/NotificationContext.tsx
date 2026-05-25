"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useAuth } from "@/lib/AuthContext";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  subscribePush,
} from "@/lib/notifications";
import { hasActiveSubscription, subscribeToPush } from "@/lib/push";
import type { OrderNotification } from "@/types";

interface NotificationContextValue {
  notifications: OrderNotification[];
  unreadCount: number;
  refresh: () => Promise<void>;
  markRead: (id: number) => Promise<void>;
  markAllRead: () => Promise<void>;
  enablePush: () => Promise<boolean>;
}

const NotificationContext = createContext<NotificationContextValue | null>(null);
const BROADCAST_CHANNEL = "kb-notifications";

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const { token, dbUser } = useAuth();
  const [notifications, setNotifications] = useState<OrderNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  const isCustomer = dbUser?.role === "customer";

  const refresh = useCallback(async () => {
    if (!token || !isCustomer) return;
    try {
      const data = await listNotifications(token);
      setNotifications(data.notifications);
      setUnreadCount(data.unread_count);
    } catch {
      /* non-fatal: bell just shows stale/empty */
    }
  }, [token, isCustomer]);

  // Initial load + refetch on window focus.
  useEffect(() => {
    if (!token || !isCustomer) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setNotifications([]);
      setUnreadCount(0);
      return;
    }
    refresh();
    const onFocus = () => refresh();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [token, isCustomer, refresh]);

  // Live-update when the service worker receives a push while the app is open.
  useEffect(() => {
    if (typeof window === "undefined" || !("BroadcastChannel" in window)) return;
    const ch = new BroadcastChannel(BROADCAST_CHANNEL);
    ch.onmessage = () => refresh();
    return () => ch.close();
  }, [refresh]);

  // Fallback poll: only while the tab is visible AND push isn't delivering
  // (push-enabled tabs rely on the BroadcastChannel ping above instead).
  useEffect(() => {
    if (!token || !isCustomer) return;
    let id: ReturnType<typeof setInterval> | null = null;
    const stop = () => {
      if (id) {
        clearInterval(id);
        id = null;
      }
    };
    const start = async () => {
      stop();
      const enabled = await hasActiveSubscription();
      if (enabled || document.visibilityState !== "visible") return;
      id = setInterval(refresh, 60_000);
    };
    const onVis = () => {
      if (document.visibilityState === "visible") start();
      else stop();
    };
    start();
    document.addEventListener("visibilitychange", onVis);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [token, isCustomer, refresh]);

  const markRead = useCallback(
    async (id: number) => {
      if (!token) return;
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, read: true } : n))
      );
      setUnreadCount((c) => Math.max(0, c - 1));
      try {
        await markNotificationRead(token, id);
      } catch {
        refresh();
      }
    },
    [token, refresh]
  );

  const markAllRead = useCallback(async () => {
    if (!token) return;
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    setUnreadCount(0);
    try {
      await markAllNotificationsRead(token);
    } catch {
      refresh();
    }
  }, [token, refresh]);

  const enablePush = useCallback(async (): Promise<boolean> => {
    if (!token) return false;
    const payload = await subscribeToPush();
    if (!payload) return false;
    try {
      await subscribePush(token, payload);
      return true;
    } catch {
      return false;
    }
  }, [token]);

  const value = useMemo(
    () => ({ notifications, unreadCount, refresh, markRead, markAllRead, enablePush }),
    [notifications, unreadCount, refresh, markRead, markAllRead, enablePush]
  );

  return (
    <NotificationContext.Provider value={value}>
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotifications(): NotificationContextValue {
  const ctx = useContext(NotificationContext);
  if (!ctx)
    throw new Error("useNotifications must be used within <NotificationProvider>");
  return ctx;
}
