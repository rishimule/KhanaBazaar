"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { suggest, type SuggestResponse } from "@/lib/searchClient";
import { SearchDropdown } from "./SearchDropdown";
import { MobileSearchOverlay } from "./MobileSearchOverlay";
import styles from "./SearchBar.module.css";

const MOBILE_BREAK = 768;
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
    // eslint-disable-next-line react-hooks/set-state-in-effect -- sync scope toggle when navigating into/out of a store page
    setScopeStore(!!storeId);
  }, [storeId]);

  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<SuggestResponse | null>(null);
  const [mobile, setMobile] = useState(false);
  const [showOverlay, setShowOverlay] = useState(false);
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
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clear stale suggestions when input empties
      setData(null);
      return;
    }
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
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
    router.push(target);
    setOpen(false);
    setShowOverlay(false);
    setQ("");
  }

  if (mobile) {
    return (
      <>
        <button
          type="button"
          aria-label={t("placeholder")}
          className={styles.iconButton}
          onClick={() => setShowOverlay(true)}
        >
          <SearchIcon />
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
    <div
      className={styles.wrap}
      role="combobox"
      aria-expanded={open}
      aria-haspopup="listbox"
    >
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
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && q.trim()) submitFull(q.trim());
          if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && (
        <SearchDropdown
          query={q}
          data={data}
          scopeStore={scopeStore}
          storeId={storeId}
          onScopeChange={setScopeStore}
          onClose={() => setOpen(false)}
          onSubmit={submitFull}
        />
      )}
    </div>
  );
}
