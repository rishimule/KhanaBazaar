"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { get } from "@/lib/api";
import { browseProducts, type BrowseResponse } from "@/lib/searchClient";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { serviceGlyph } from "@/lib/serviceGlyph";
import { ScrollRail } from "@/components/ScrollRail";
import { CategoryCarousel } from "@/components/CategoryCarousel";
import { SearchResultsGrid } from "@/components/search/SearchResultsGrid";
import { SearchFilters } from "@/components/search/SearchFilters";
import { DeliveryLocationPicker } from "@/components/DeliveryLocationPicker";
import { Service } from "@/types";
import styles from "./page.module.css";

function ProductsInner() {
  const t = useTranslations("Products");
  const locale = useLocale();
  const sp = useSearchParams();
  const { location } = useDeliveryLocation();
  const [pickerOpen, setPickerOpen] = useState(false);

  const serviceSlug = sp.get("service");
  const categoryId = sp.get("category");

  const [services, setServices] = useState<Service[]>([]);
  const [browse, setBrowse] = useState<BrowseResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    get<Service[]>("/api/v1/catalog/services")
      .then((rows) =>
        setServices(
          rows
            .filter((s) => s.is_active !== false)
            .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id),
        ),
      )
      .catch(() => setServices([]));
  }, [locale]);

  const activeSlug = serviceSlug ?? services[0]?.slug ?? null;
  const activeService = useMemo(
    () => services.find((s) => s.slug === activeSlug) ?? null,
    [services, activeSlug],
  );

  const seeAllMode = Boolean(categoryId && activeService);

  // See-all grid: subcategory chips come from the active category in the
  // browse payload (only subcategories with in-area products).
  const activeCategory =
    browse?.categories.find((c) => String(c.id) === categoryId) ?? null;
  const activeSubId = sp.get("subcategory")
    ? Number(sp.get("subcategory"))
    : null;

  function subHref(subId: number | null): string {
    const params = new URLSearchParams(Array.from(sp.entries()));
    if (subId === null) params.delete("subcategory");
    else params.set("subcategory", String(subId));
    return `/products?${params.toString()}`;
  }

  // Browse data for the active service — drives carousels, and supplies the
  // category's subcategory list for the see-all grid's filter chips.
  useEffect(() => {
    if (!activeService) return;
    let cancel = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- show skeleton synchronously while fetching
    setLoading(true);
    browseProducts(
      { serviceId: activeService.id, lat: location?.lat, lng: location?.lng },
      locale,
    )
      .then((res) => {
        if (!cancel) setBrowse(res);
      })
      .catch(() => {
        if (!cancel) setBrowse(null);
      })
      .finally(() => {
        if (!cancel) setLoading(false);
      });
    return () => {
      cancel = true;
    };
  }, [activeService, categoryId, location, locale]);

  return (
    <div className={styles.page}>
      <div className={styles.inner}>
        <h1 className={styles.title}>{t("title")}</h1>

        {!location && (
          <div className={styles.banner}>
            <span>⚠ {t("setLocationBanner")}</span>
            <button
              type="button"
              className={styles.bannerBtn}
              onClick={() => setPickerOpen(true)}
            >
              {t("setLocationCta")}
            </button>
          </div>
        )}

        {services.length > 0 && (
          <div className={styles.svcSection}>
            <ScrollRail
              ariaLabel={t("title")}
              leftLabel={t("scrollLeft")}
              rightLabel={t("scrollRight")}
            >
              {services.map((s) => {
                const active = s.slug === activeSlug;
                return (
                  <Link
                    key={s.id}
                    href={`/products?service=${encodeURIComponent(s.slug)}`}
                    className={`${styles.svcTile} ${active ? styles.svcTileActive : ""}`}
                    aria-current={active ? "true" : undefined}
                  >
                    <span className={styles.svcTileGlyph} aria-hidden>
                      {serviceGlyph(s.slug)}
                    </span>
                    <span className={styles.svcTileLabel}>{s.name}</span>
                  </Link>
                );
              })}
            </ScrollRail>
          </div>
        )}

        {seeAllMode && activeService ? (
          <>
            <Link
              href={`/products?service=${encodeURIComponent(activeService.slug)}`}
              className={styles.backLink}
            >
              ‹ {activeService.name}
            </Link>
            {activeCategory && (
              <h2 className={styles.categoryTitle}>{activeCategory.name}</h2>
            )}
            {activeCategory && activeCategory.subcategories.length > 0 && (
              <div className={styles.chipRow}>
                <ScrollRail
                  ariaLabel={activeCategory.name}
                  leftLabel={t("scrollLeft")}
                  rightLabel={t("scrollRight")}
                >
                  <Link
                    href={subHref(null)}
                    className={`${styles.chip} ${activeSubId === null ? styles.chipActive : ""}`}
                    aria-current={activeSubId === null ? "true" : undefined}
                  >
                    {t("allSubcategories")}
                  </Link>
                  {activeCategory.subcategories.map((s) => (
                    <Link
                      key={s.id}
                      href={subHref(s.id)}
                      className={`${styles.chip} ${activeSubId === s.id ? styles.chipActive : ""}`}
                      aria-current={activeSubId === s.id ? "true" : undefined}
                    >
                      {s.name}
                    </Link>
                  ))}
                </ScrollRail>
              </div>
            )}
            <SearchFilters />
            <div className={styles.gridWrap}>
              <SearchResultsGrid
                q=""
                serviceId={activeService.id}
                categoryId={Number(categoryId)}
                subcategoryId={activeSubId ?? undefined}
                minPrice={sp.get("min_price") ? Number(sp.get("min_price")) : undefined}
                maxPrice={sp.get("max_price") ? Number(sp.get("max_price")) : undefined}
                sort={sp.get("sort") ?? "relevance"}
              />
            </div>
          </>
        ) : (
          <>
            {loading && <div className={styles.empty}>{t("loading")}</div>}
            {!loading && browse && browse.categories.length === 0 && (
              <div className={styles.empty}>{t("empty")}</div>
            )}
            {!loading &&
              browse &&
              activeService &&
              browse.categories.map((cat) => (
                <CategoryCarousel
                  key={cat.id}
                  category={cat}
                  serviceId={activeService.id}
                  serviceSlug={activeService.slug}
                />
              ))}
          </>
        )}

        <DeliveryLocationPicker
          open={pickerOpen}
          onClose={() => setPickerOpen(false)}
        />
      </div>
    </div>
  );
}

export default function ProductsPage() {
  return (
    <Suspense fallback={<div className={styles.page} />}>
      <ProductsInner />
    </Suspense>
  );
}
