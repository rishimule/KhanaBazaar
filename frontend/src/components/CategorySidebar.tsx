"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import styles from "./CategorySidebar.module.css";

export interface SidebarItem {
  id: string | number;
  icon: string;
  label: string;
}

interface Props {
  items: SidebarItem[];
  activeId?: string | number | null;
  onSelect?: (id: string | number) => void;
}

export default function CategorySidebar({ items, activeId, onSelect }: Props) {
  return (
    <nav className={styles.rail} aria-label="Categories">
      {items.map((item) => {
        const active = activeId === item.id;
        return (
          <button
            key={item.id}
            type="button"
            className={`${styles.item} ${active ? styles.itemActive : ""}`}
            onClick={() => onSelect?.(item.id)}
            aria-current={active ? "true" : undefined}
          >
            <span className={styles.icon} aria-hidden>{item.icon}</span>
            <span className={styles.label}>{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
