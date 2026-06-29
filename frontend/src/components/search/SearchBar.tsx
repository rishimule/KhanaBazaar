"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { useSearchOverlay } from "@/lib/SearchOverlayContext";
import { suggest, type SuggestResponse } from "@/lib/searchClient";
import { SearchDropdown } from "./SearchDropdown";
import { MobileSearchOverlay } from "./MobileSearchOverlay";
import styles from "./SearchBar.module.css";

const MOBILE_BREAK = 1024;
const DEBOUNCE_MS = 180;

function SearchIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}

export function SearchBar() {
  const t = useTranslations("Search");
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  const { location } = useDeliveryLocation();

  const storeMatch = pathname?.match(/\/stores\/(\d+)/);
  const storeId = storeMatch ? Number(storeMatch[1]) : undefined;

  const [scopeStore, setScopeStore] = useState<boolean>(!!storeId);
  useEffect(() => {
    // sync scope toggle when navigating into/out of a store page
    setScopeStore(!!storeId);
  }, [storeId]);

  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<SuggestResponse | null>(null);
  const [mobile, setMobile] = useState(false);
  const { open: showOverlay, setOpen: setShowOverlay } = useSearchOverlay();
  const [activeIndex, setActiveIndex] = useState(-1);
  const debounceRef = useRef<number | null>(null);

  useEffect(() => {
    function check() {
      setMobile(window.innerWidth < MOBILE_BREAK);
    }
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  useEffect(() => {
    if (!q.trim()) {
      // clear stale suggestions when input empties
      setData(null);
      return;
    }
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    // Clear stale dropdown content immediately so the user never sees previous
    // query's results while the new request is in flight.
    setData(null);
    debounceRef.current = window.setTimeout(async () => {
      try {
        const res = await suggest({
          q: q.trim(),
          lat: location?.lat,
          lng: location?.lng,
          storeId: scopeStore ? storeId : undefined,
          locale,
        });
        if (res) setData(res);
      } catch {
        setData(null);
      }
    }, DEBOUNCE_MS);
  }, [q, location, scopeStore, storeId, locale]);

  function submitFull(term: string) {
    const target =
      scopeStore && storeId
        ? `/${locale}/stores/${storeId}?q=${encodeURIComponent(term)}`
        : `/${locale}/search?q=${encodeURIComponent(term)}`;
    // Record this submission as a recent search.
    import("@/lib/recentSearches").then((m) => m.add(term)).catch(() => undefined);
    router.push(target);
    setOpen(false);
    setShowOverlay(false);
    setQ("");
  }

  // Flat row count for keyboard navigation across the dropdown's
  // products + stores sections. Suggestions and recents stay click-only.
  const navProducts = data?.products ?? [];
  const navStores = data?.stores ?? [];
  const navTotal = navProducts.length + navStores.length;

  function handleArrow(direction: 1 | -1) {
    if (navTotal === 0) return;
    setActiveIndex((idx) => {
      const next = idx + direction;
      if (next < 0) return navTotal - 1;
      if (next >= navTotal) return 0;
      return next;
    });
  }

  function activateRow() {
    if (activeIndex < 0) return false;
    if (activeIndex < navProducts.length) {
      const p = navProducts[activeIndex];
      router.push(`/${locale}/search/product/${p.id}`);
      setOpen(false);
      setQ("");
      return true;
    }
    const s = navStores[activeIndex - navProducts.length];
    if (s) {
      router.push(`/${locale}/stores/${s.id}`);
      setOpen(false);
      setQ("");
      return true;
    }
    return false;
  }

  if (mobile) {
    return (
      <>
        <button
          type="button"
          aria-label={t("placeholder")}
          className={styles.mobilePill}
          onClick={() => setShowOverlay(true)}
        >
          <span className={styles.mobilePillIcon}>
            <SearchIcon />
          </span>
          <span className={styles.mobilePillPlaceholder}>{t("placeholder")}</span>
        </button>
        {showOverlay && (
          <MobileSearchOverlay
            scopeStore={scopeStore}
            storeId={storeId}
            onScopeChange={setScopeStore}
            onClose={() => setShowOverlay(false)}
            onSubmit={submitFull}
          />
        )}
      </>
    );
  }

  return (
    <div className={styles.wrap}>
      <span className={styles.searchIcon}>
        <SearchIcon />
      </span>
      <input
        type="search"
        className={styles.input}
        placeholder={t("placeholder")}
        value={q}
        maxLength={100}
        autoComplete="off"
        role="combobox"
        aria-expanded={open}
        aria-controls="kb-search-listbox"
        aria-activedescendant={
          activeIndex >= 0 ? `kb-search-opt-${activeIndex}` : undefined
        }
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
          setActiveIndex(-1);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            handleArrow(1);
            return;
          }
          if (e.key === "ArrowUp") {
            e.preventDefault();
            handleArrow(-1);
            return;
          }
          if (e.key === "Enter") {
            if (activateRow()) return;
            if (q.trim()) submitFull(q.trim());
            return;
          }
          if (e.key === "Escape") {
            setOpen(false);
            setActiveIndex(-1);
          }
        }}
      />
      {open && (
        <SearchDropdown
          query={q}
          data={data}
          scopeStore={scopeStore}
          storeId={storeId}
          activeIndex={activeIndex}
          listboxId="kb-search-listbox"
          onScopeChange={setScopeStore}
          onClose={() => setOpen(false)}
          onSubmit={submitFull}
        />
      )}
    </div>
  );
}
