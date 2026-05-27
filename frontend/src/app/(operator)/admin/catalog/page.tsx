"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { useTranslations } from "next-intl";
import type { CatalogEntity, EntityKind } from "@/types";
import { Breadcrumb, type BreadcrumbCrumb } from "./_components/Breadcrumb";
import { CatalogTable } from "./_components/CatalogTable";
import { useAncestorNames } from "./_hooks/useAncestorNames";
import styles from "./page.module.css";

function readNumber(sp: URLSearchParams, key: string): number | undefined {
  const v = sp.get(key);
  if (v == null || v === "") return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

function buildHref(next: {
  service?: number;
  category?: number;
  subcategory?: number;
}): string {
  const p = new URLSearchParams();
  if (next.service) p.set("service", String(next.service));
  if (next.category) p.set("category", String(next.category));
  if (next.subcategory) p.set("subcategory", String(next.subcategory));
  const qs = p.toString();
  return `/admin/catalog${qs ? `?${qs}` : ""}`;
}

export default function AdminCatalogPage() {
  const t = useTranslations("Admin.catalog");
  const sp = useSearchParams();
  const router = useRouter();

  const serviceId = readNumber(sp, "service");
  const categoryId = readNumber(sp, "category");
  const subcategoryId = readNumber(sp, "subcategory");

  const level: EntityKind = subcategoryId
    ? "product"
    : categoryId
      ? "subcategory"
      : serviceId
        ? "category"
        : "service";

  const parentId = subcategoryId ?? categoryId ?? serviceId;
  const ancestors = useAncestorNames(serviceId, categoryId, subcategoryId);

  const crumbs: BreadcrumbCrumb[] = useMemo(() => {
    const out: BreadcrumbCrumb[] = [{ label: t("services"), href: "/admin/catalog" }];
    if (serviceId) {
      out.push({
        label: ancestors.service || t("serviceFallback", { id: serviceId }),
        href: buildHref({ service: serviceId }),
      });
    }
    if (categoryId) {
      out.push({
        label: ancestors.category || t("categoryFallback", { id: categoryId }),
        href: buildHref({ service: serviceId, category: categoryId }),
      });
    }
    if (subcategoryId) {
      out.push({
        label: ancestors.subcategory || t("subcategoryFallback", { id: subcategoryId }),
        href: buildHref({
          service: serviceId,
          category: categoryId,
          subcategory: subcategoryId,
        }),
      });
    }
    return out;
  }, [serviceId, categoryId, subcategoryId, ancestors, t]);

  function onRowOpen(row: CatalogEntity) {
    if (level === "service") {
      router.push(buildHref({ service: row.id }));
    } else if (level === "category") {
      router.push(buildHref({ service: serviceId, category: row.id }));
    } else if (level === "subcategory") {
      router.push(
        buildHref({
          service: serviceId,
          category: categoryId,
          subcategory: row.id,
        }),
      );
    }
  }

  return (
    <div className={styles.page}>
      <Breadcrumb crumbs={crumbs} />
      <CatalogTable
        entity={level}
        parentId={parentId}
        serviceContext={serviceId}
        onRowOpen={level === "product" ? undefined : onRowOpen}
      />
    </div>
  );
}
