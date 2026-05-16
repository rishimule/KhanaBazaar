"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { suggest, type SuggestResponse } from "@/lib/searchClient";
import { SearchDropdown } from "./SearchDropdown";
import styles from "./MobileSearchOverlay.module.css";

type Props = {
  scopeStore: boolean;
  storeId: number | undefined;
  onScopeChange: (v: boolean) => void;
  onClose: () => void;
  onSubmit: (term: string) => void;
};

export function MobileSearchOverlay({
  scopeStore,
  storeId,
  onScopeChange,
  onClose,
  onSubmit,
}: Props) {
  const t = useTranslations("Search");
  const locale = useLocale();
  const { location } = useDeliveryLocation();
  const [q, setQ] = useState("");
  const [data, setData] = useState<SuggestResponse | null>(null);
  const debounceRef = useRef<number | null>(null);

  useEffect(() => {
    // Push a history entry; back-button closes the overlay.
    window.history.pushState({ searchOverlay: true }, "");
    function onPop() {
      onClose();
    }
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [onClose]);

  useEffect(() => {
    if (!q.trim()) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clear stale results when input empties
      setData(null);
      return;
    }
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    // Clear stale dropdown content on every keystroke (no flicker).
    // eslint-disable-next-line react-hooks/set-state-in-effect -- discard stale data on every new keystroke
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
        /* swallow */
      }
    }, 180);
  }, [q, location, scopeStore, storeId, locale]);

  return (
    <div className={styles.overlay}>
      <header className={styles.header}>
        <button
          type="button"
          aria-label="Close search"
          className={styles.backBtn}
          onClick={onClose}
        >
          ←
        </button>
        <input
          autoFocus
          type="search"
          maxLength={100}
          placeholder={t("placeholder")}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && q.trim()) onSubmit(q.trim());
          }}
          className={styles.input}
        />
      </header>
      <div className={styles.results}>
        <SearchDropdown
          query={q}
          data={data}
          scopeStore={scopeStore}
          storeId={storeId}
          onScopeChange={onScopeChange}
          onClose={onClose}
          onSubmit={onSubmit}
        />
      </div>
    </div>
  );
}
