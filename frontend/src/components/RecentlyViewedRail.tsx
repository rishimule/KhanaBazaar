"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import Link from "next/link";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { getRecentlyViewed, type RecentlyViewedEntry } from "@/lib/recentlyViewed";
import styles from "./RecentlyViewedRail.module.css";

export default function RecentlyViewedRail() {
  const t = useTranslations("Account.dashboard");
  const [items, setItems] = useState<RecentlyViewedEntry[]>([]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time hydration from localStorage on mount
    setItems(getRecentlyViewed().slice(0, 6));
  }, []);

  if (items.length === 0) return null;

  return (
    <section className={styles.rail}>
      <h2 className={styles.title}>{t("recentlyViewed")}</h2>
      <div className={styles.list}>
        {items.map((it) => (
          <Link
            key={it.product_id}
            href={`/stores/${it.store_id}/p/${it.product_id}`}
            className={styles.card}
          >
            {it.image_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={it.image_url}
                alt=""
                className={styles.img}
                referrerPolicy="no-referrer"
              />
            )}
            <span className={styles.name}>{it.name}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
