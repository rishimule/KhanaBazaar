"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { getCatalog, listCatalog } from "@/lib/catalog";
import type { CatalogEntity, EntityKind } from "@/types";
import styles from "./ParentPicker.module.css";

interface Props {
  parentEntity: EntityKind;
  value: number | null;
  onChange: (id: number) => void;
  /** Extra params to scope the search (e.g. service_id when picking a category). */
  filterParams?: { service_id?: number; category_id?: number };
}

export function ParentPicker({
  parentEntity,
  value,
  onChange,
  filterParams = {},
}: Props) {
  const t = useTranslations("Admin.catalog");
  const { token } = useAuth();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [items, setItems] = useState<CatalogEntity[]>([]);
  const [selectedItem, setSelectedItem] = useState<CatalogEntity | null>(null);
  const filterKey = JSON.stringify(filterParams);
  const reqIdRef = useRef(0);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  // Resolve current selection so the trigger always shows a real name.
  useEffect(() => {
    if (!value) {
      setSelectedItem(null);
      return;
    }
    let cancelled = false;
    getCatalog(parentEntity, value, token)
      .then((item) => {
        if (!cancelled) setSelectedItem(item);
      })
      .catch(() => {
        if (!cancelled) setSelectedItem(null);
      });
    return () => {
      cancelled = true;
    };
  }, [value, parentEntity, token]);

  // Fetch filtered list whenever the popover is open and q/filter changes.
  useEffect(() => {
    if (!open) return;
    const reqId = ++reqIdRef.current;
    const t = setTimeout(() => {
      listCatalog(
        parentEntity,
        { q: q || undefined, is_active: true, page_size: 25, ...filterParams },
        token,
      )
        .then((res) => {
          if (reqIdRef.current !== reqId) return;
          setItems(res.items);
        })
        .catch(() => {
          if (reqIdRef.current !== reqId) return;
          setItems([]);
        });
    }, 150);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, parentEntity, filterKey, token, open]);

  // Click outside closes the popover.
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (!wrapRef.current) return;
      if (!wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  function handleSelect(item: CatalogEntity) {
    onChange(item.id);
    setSelectedItem(item);
    setOpen(false);
    setQ("");
  }

  const triggerLabel = selectedItem
    ? `${selectedItem.name}`
    : t("choosePlaceholder");

  return (
    <div className={styles.wrap} ref={wrapRef}>
      <button
        type="button"
        className={styles.trigger}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className={styles.triggerLabel}>{triggerLabel}</span>
        {selectedItem && (
          <span className={styles.triggerSlug}>{selectedItem.slug}</span>
        )}
        <span className={styles.caret} aria-hidden>
          ▾
        </span>
      </button>

      {open && (
        <div className={styles.popover} role="listbox">
          <input
            type="text"
            autoFocus
            placeholder={t("pickerSearchPlaceholder")}
            className={styles.search}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <ul className={styles.list}>
            {items.length === 0 && (
              <li className={styles.empty}>{t("noMatches")}</li>
            )}
            {items.map((i) => {
              const isSelected = i.id === value;
              return (
                <li key={i.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    className={`${styles.option} ${
                      isSelected ? styles.optionSelected : ""
                    }`}
                    onClick={() => handleSelect(i)}
                  >
                    <span className={styles.optionName}>{i.name}</span>
                    <span className={styles.optionSlug}>{i.slug}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
