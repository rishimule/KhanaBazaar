"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useEffect, useRef, useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { useAuth } from "@/lib/AuthContext";
import { useNotifications } from "@/lib/NotificationContext";
import { pushSupported } from "@/lib/push";
import styles from "./NotificationBell.module.css";

export default function NotificationBell() {
  const { dbUser } = useAuth();
  const { notifications, unreadCount, markRead, markAllRead, enablePush } =
    useNotifications();
  const [open, setOpen] = useState(false);
  const [canEnablePush, setCanEnablePush] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();

  const isCustomer = dbUser?.role === "customer";

  useEffect(() => {
    if (!isCustomer) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCanEnablePush(
      pushSupported() &&
        typeof Notification !== "undefined" &&
        Notification.permission === "default"
    );
  }, [isCustomer, open]);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  if (!isCustomer) return null;

  const handleItemClick = (id: number, orderId: number | null) => {
    markRead(id);
    setOpen(false);
    router.push(orderId ? `/account/orders/${orderId}` : "/account/orders");
  };

  return (
    <div className={styles.wrap} ref={ref}>
      <button
        type="button"
        className={styles.bellBtn}
        aria-label="Notifications"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unreadCount > 0 && (
          <span className={styles.badge}>{unreadCount > 9 ? "9+" : unreadCount}</span>
        )}
      </button>

      {open && (
        <div className={styles.panel} role="menu">
          <div className={styles.panelHead}>
            <span>Notifications</span>
            {unreadCount > 0 && (
              <button type="button" className={styles.linkBtn} onClick={markAllRead}>
                Mark all read
              </button>
            )}
          </div>

          {canEnablePush && (
            <button
              type="button"
              className={styles.enablePush}
              onClick={async () => {
                const ok = await enablePush();
                if (ok) setCanEnablePush(false);
              }}
            >
              🔔 Turn on order alerts
            </button>
          )}

          {notifications.length === 0 ? (
            <div className={styles.empty}>No notifications yet.</div>
          ) : (
            <ul className={styles.list}>
              {notifications.map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    className={`${styles.item} ${n.read ? "" : styles.unread}`}
                    onClick={() => handleItemClick(n.id, n.order_id)}
                  >
                    <span className={styles.itemTitle}>{n.title}</span>
                    <span className={styles.itemBody}>{n.body}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
