"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { useNotifications } from "@/lib/NotificationContext";
import { usePushOptIn } from "@/components/pwa/usePushOptIn";
import styles from "./NotificationBell.module.css";

function BellIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

export default function NotificationBell() {
  const t = useTranslations("Notifications");
  const router = useRouter();
  const { notifications, unreadCount, markRead, markAllRead } = useNotifications();
  const { state, enable, openInstall } = usePushOptIn();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const onItem = (id: number, orderId: number | null) => {
    void markRead(id);
    setOpen(false);
    router.push(orderId ? `/account/orders/${orderId}` : "/account/orders");
  };

  const showBanner =
    state === "default" || state === "needs_install_ios" || state === "denied";

  return (
    <div className={styles.wrap} ref={ref}>
      <button
        type="button"
        className={styles.bellBtn}
        aria-label={t("ariaLabel")}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <BellIcon />
        {unreadCount > 0 && (
          <span className={styles.badge}>{unreadCount > 99 ? "99+" : unreadCount}</span>
        )}
      </button>

      {open && (
        <div className={styles.panel} role="dialog" aria-label={t("title")}>
          <div className={styles.panelHead}>
            <span>{t("title")}</span>
            {unreadCount > 0 && (
              <button type="button" className={styles.linkBtn} onClick={() => void markAllRead()}>
                {t("markAllRead")}
              </button>
            )}
          </div>

          {showBanner && (
            <div className={styles.enableBanner}>
              <strong className={styles.bannerTitle}>{t("enableTitle")}</strong>
              <p className={styles.bannerSub}>
                {state === "denied" ? t("blocked") : t("enableBody")}
              </p>
              {state === "default" && (
                <button type="button" className={styles.enableCta} onClick={() => void enable()}>
                  {t("enableCta")}
                </button>
              )}
              {state === "needs_install_ios" && (
                <button type="button" className={styles.enableCta} onClick={openInstall}>
                  {t("installCta")}
                </button>
              )}
            </div>
          )}

          <ul className={styles.list}>
            {notifications.length === 0 ? (
              <li className={styles.empty}>{t("empty")}</li>
            ) : (
              notifications.map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    className={`${styles.item} ${n.read ? "" : styles.unread}`}
                    onClick={() => onItem(n.id, n.order_id)}
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
