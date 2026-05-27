"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useTranslations } from "next-intl";
import styles from "./Breadcrumb.module.css";

export interface BreadcrumbCrumb {
  label: string;
  href?: string;
}

export function Breadcrumb({ crumbs }: { crumbs: BreadcrumbCrumb[] }) {
  const t = useTranslations("Admin.catalog");
  return (
    <nav aria-label={t("breadcrumbAria")} className={styles.bar}>
      {crumbs.map((c, i) => {
        const last = i === crumbs.length - 1;
        return (
          <span key={i} className={styles.crumb}>
            {c.href && !last ? (
              <Link href={c.href}>{c.label}</Link>
            ) : (
              <span aria-current={last ? "page" : undefined}>{c.label}</span>
            )}
            {!last && <span className={styles.sep}>/</span>}
          </span>
        );
      })}
    </nav>
  );
}
