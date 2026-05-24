"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import * as recent from "@/lib/recentSearches";
import { logClick, type SuggestResponse } from "@/lib/searchClient";
import styles from "./SearchDropdown.module.css";

type Props = {
  query: string;
  data: SuggestResponse | null;
  scopeStore: boolean;
  storeId: number | undefined;
  activeIndex?: number;
  listboxId?: string;
  /** Render in document flow (mobile overlay) instead of an absolute dropdown. */
  inline?: boolean;
  onScopeChange: (v: boolean) => void;
  onClose: () => void;
  onSubmit: (term: string) => void;
};

export function SearchDropdown({
  query,
  data,
  scopeStore,
  storeId,
  activeIndex = -1,
  listboxId = "kb-search-listbox",
  inline = false,
  onScopeChange,
  onClose,
  onSubmit,
}: Props) {
  const t = useTranslations("Search");
  const locale = useLocale();
  const [recents, setRecents] = useState<string[]>([]);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- refresh recents when query toggles between empty/non-empty
    setRecents(recent.list());
  }, [query]);

  useEffect(() => {
    // The mobile overlay owns its own dismissal (back button / popstate); the
    // outside-click + scroll-to-close handlers are desktop-dropdown behavior.
    if (inline) return;
    function handleOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    function handleScroll() {
      onClose();
    }
    document.addEventListener("mousedown", handleOutside);
    document.addEventListener("scroll", handleScroll, true);
    return () => {
      document.removeEventListener("mousedown", handleOutside);
      document.removeEventListener("scroll", handleScroll, true);
    };
  }, [onClose, inline]);

  const showRecents = !query.trim() && recents.length > 0;
  const showEmptyPrompt = !query.trim() && recents.length === 0;

  return (
    <div
      ref={ref}
      id={listboxId}
      role="listbox"
      className={inline ? `${styles.dropdown} ${styles.dropdownInline}` : styles.dropdown}
    >
      {storeId !== undefined && (
        <div className={styles.scopeToggle}>
          <button
            type="button"
            className={scopeStore ? styles.scopeActive : styles.scopeBtn}
            onClick={() => onScopeChange(true)}
            aria-pressed={scopeStore}
          >
            {t("inThisStore")}
          </button>
          <button
            type="button"
            className={!scopeStore ? styles.scopeActive : styles.scopeBtn}
            onClick={() => onScopeChange(false)}
            aria-pressed={!scopeStore}
          >
            {t("allStores")}
          </button>
        </div>
      )}

      {showEmptyPrompt && (
        <div className={styles.empty}>{t("startTyping")}</div>
      )}

      {showRecents && (
        <section>
          <header className={styles.sectionHeader}>
            <span>{t("recent")}</span>
            <button
              type="button"
              className={styles.clearAllBtn}
              onClick={() => {
                recent.clear();
                setRecents([]);
              }}
            >
              {t("clearAll")}
            </button>
          </header>
          {recents.map((r) => (
            <div
              key={r}
              role="option"
              aria-selected={false}
              className={styles.row}
              onClick={() => {
                recent.add(r);
                onSubmit(r);
              }}
            >
              <span>{r}</span>
              <button
                type="button"
                aria-label={t("clear")}
                className={styles.removeBtn}
                onClick={(e) => {
                  e.stopPropagation();
                  recent.remove(r);
                  setRecents(recent.list());
                }}
              >
                ✕
              </button>
            </div>
          ))}
        </section>
      )}

      {data && data.terms.length > 0 && (
        <section>
          <header className={styles.sectionHeader}>{t("suggestions")}</header>
          {data.terms.map((term) => (
            <div
              key={`${term.kind}-${term.text}`}
              role="option"
              aria-selected={false}
              className={styles.row}
              onClick={() => {
                recent.add(term.text);
                onSubmit(term.text);
              }}
            >
              🔍 {term.text}
            </div>
          ))}
        </section>
      )}

      {data && data.products.length > 0 && (
        <section>
          <header className={styles.sectionHeader}>{t("products")}</header>
          {data.products.map((p, i) => (
            <Link
              key={p.id}
              id={`kb-search-opt-${i}`}
              href={`/${locale}/search/product/${p.id}`}
              role="option"
              aria-selected={activeIndex === i}
              className={
                activeIndex === i
                  ? `${styles.productRow} ${styles.rowActive}`
                  : styles.productRow
              }
              onClick={() => {
                logClick({
                  query_id: data.query_id,
                  clicked_product_id: p.id,
                  position: i,
                });
              }}
            >
              {p.image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={p.image_url}
                  alt=""
                  width={40}
                  height={40}
                  loading="lazy"
                  decoding="async"
                  referrerPolicy="no-referrer"
                  className={styles.thumb}
                />
              ) : (
                <span className={styles.thumbFallback} aria-hidden>
                  🛒
                </span>
              )}
              <span className={styles.productMeta}>
                <span className={styles.productName}>{p.name}</span>
                {p.best_store && (
                  <span className={styles.productSub}>
                    {p.best_store.name}
                    {" · "}
                    {p.best_store.is_available ? "in stock" : t("outOfStock")}
                  </span>
                )}
              </span>
              <span className={styles.price}>₹{p.min_price.toFixed(0)}</span>
            </Link>
          ))}
        </section>
      )}

      {data && data.stores.length > 0 && (
        <section>
          <header className={styles.sectionHeader}>{t("stores")}</header>
          {data.stores.map((s, i) => {
            const flatIdx = (data?.products.length ?? 0) + i;
            return (
            <Link
              key={s.id}
              id={`kb-search-opt-${flatIdx}`}
              href={`/${locale}/stores/${s.id}`}
              role="option"
              aria-selected={activeIndex === flatIdx}
              className={
                activeIndex === flatIdx
                  ? `${styles.row} ${styles.rowActive}`
                  : styles.row
              }
              onClick={() => {
                logClick({
                  query_id: data.query_id,
                  clicked_store_id: s.id,
                  position: i,
                });
              }}
            >
              <span>🏪 {s.name}</span>
              {s.distance_km !== null && <span>{s.distance_km} km</span>}
            </Link>
            );
          })}
        </section>
      )}

      {query.trim() && (
        <div
          className={styles.seeAll}
          role="option"
          aria-selected={false}
          onClick={() => {
            recent.add(query.trim());
            onSubmit(query.trim());
          }}
        >
          {t("seeAll", { q: query.trim() })} →
        </div>
      )}
    </div>
  );
}
