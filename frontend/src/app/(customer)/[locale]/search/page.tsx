"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { SearchFilters } from "@/components/search/SearchFilters";
import { SearchResultsGrid } from "@/components/search/SearchResultsGrid";
import styles from "./page.module.css";

function SearchPageInner() {
  const sp = useSearchParams();
  const t = useTranslations("Search");
  const q = sp.get("q") ?? "";
  const serviceId = sp.get("service_id");
  const categoryId = sp.get("category_id");
  const minPrice = sp.get("min_price");
  const maxPrice = sp.get("max_price");
  const sort = sp.get("sort") ?? "relevance";

  return (
    <main className={styles.page}>
      <h1 className={styles.title}>{t("resultsTitle", { q })}</h1>
      <SearchFilters />
      <SearchResultsGrid
        q={q}
        serviceId={serviceId ? Number(serviceId) : undefined}
        categoryId={categoryId ? Number(categoryId) : undefined}
        minPrice={minPrice ? Number(minPrice) : undefined}
        maxPrice={maxPrice ? Number(maxPrice) : undefined}
        sort={sort}
      />
    </main>
  );
}

export default function GlobalSearchPage() {
  return (
    <Suspense fallback={<main className={styles.page}>Loading…</main>}>
      <SearchPageInner />
    </Suspense>
  );
}
