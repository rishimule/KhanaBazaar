// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/AuthContext";
import {
  listSellerNotifications,
  markAllSellerNotificationsRead,
  markSellerNotificationRead,
} from "@/lib/notifications";
import type { OrderNotification } from "@/types";
import styles from "@/components/NotificationBell.module.css";

const POLL_MS = 60_000;

function BellIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

// Self-contained seller bell — the customer NotificationContext is customer-only
// (and web-push stays customer-only), so this fetches/polls the seller feed
// directly. Operator English-only copy.
export default function SellerNotificationBell() {
  const { token } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<OrderNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [feedFailed, setFeedFailed] = useState(false);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const res = await listSellerNotifications(token);
      setItems(res.notifications);
      setUnread(res.unread_count);
      setFeedFailed(false);
    } catch {
      // Not "best-effort": hiding this showed 0 unread and "No notifications
      // yet" while the seller's store was being suspended for non-payment.
      // The count goes indeterminate rather than falsely reading zero.
      setFeedFailed(true);
    }
  }, [token]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount seller feed
    void load();
  }, [load]);

  useEffect(() => {
    const iv = setInterval(() => void load(), POLL_MS);
    const onFocus = () => void load();
    window.addEventListener("focus", onFocus);
    return () => {
      clearInterval(iv);
      window.removeEventListener("focus", onFocus);
    };
  }, [load]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const onItem = (id: number, orderId: number | null, wasUnread: boolean) => {
    setOpen(false);
    // The local state below is optimistic. If the write failed, re-reading the
    // feed is what keeps the badge honest — swallowing left the count claiming
    // a notification had been read when the server still had it unread.
    if (token) void markSellerNotificationRead(token, id).catch(() => void load());
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
    if (wasUnread) setUnread((u) => Math.max(0, u - 1));
    router.push(orderId ? `/seller/orders/${orderId}` : "/seller/plan");
  };

  const onMarkAll = () => {
    if (token) void markAllSellerNotificationsRead(token).catch(() => void load());
    setItems((prev) => prev.map((n) => ({ ...n, read: true })));
    setUnread(0);
  };

  return (
    <div className={styles.wrap} ref={ref}>
      <button
        type="button"
        className={styles.bellBtn}
        aria-label="Notifications"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <BellIcon />
        {feedFailed ? (
          <span className={styles.badge} aria-live="polite" title="Couldn't load notifications">
            !
          </span>
        ) : (
          unread > 0 && (
            <span className={styles.badge} aria-live="polite">
              {unread > 99 ? "99+" : unread}
            </span>
          )
        )}
      </button>

      {open && (
        <div className={styles.panel} role="dialog" aria-label="Notifications">
          <div className={styles.panelHead}>
            <span>Notifications</span>
            {unread > 0 && (
              <button type="button" className={styles.linkBtn} onClick={onMarkAll}>
                Mark all read
              </button>
            )}
          </div>

          <ul className={styles.list}>
            {feedFailed && items.length === 0 ? (
              // Operator English-only copy, matching this file's convention.
              <li className={styles.empty}>
                Couldn&apos;t load your notifications.{" "}
                <button type="button" className={styles.linkBtn} onClick={() => void load()}>
                  Retry
                </button>
              </li>
            ) : items.length === 0 ? (
              <li className={styles.empty}>No notifications yet</li>
            ) : (
              items.map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    className={`${styles.item} ${n.read ? "" : styles.unread}`}
                    onClick={() => onItem(n.id, n.order_id, !n.read)}
                  >
                    {n.image_url && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        className={styles.thumb}
                        src={n.image_url}
                        alt=""
                        referrerPolicy="no-referrer"
                      />
                    )}
                    <span className={styles.itemTitle}>{n.title}</span>
                    <span className={styles.itemBody}>{n.body}</span>
                  </button>
                  {n.cta_url && (
                    <a
                      className={styles.cta}
                      href={n.cta_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {n.cta_label || n.cta_url}
                    </a>
                  )}
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
