// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { notFound } from "next/navigation";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import type { Metadata } from "next";
import { ApiError } from "@/lib/api";
import { getStoreProduct } from "@/lib/api/products";
import ProductDetail from "@/components/ProductDetail/ProductDetail";
import CrownBadge from "@/components/CrownBadge";
import { COMPANY_NAME } from "@/lib/brand";
import styles from "./ProductFullPage.module.css";

type Params = Promise<{ locale: string; id: string; productId: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { id, productId } = await params;
  const storeId = Number(id);
  const pid = Number(productId);
  if (!Number.isFinite(storeId) || !Number.isFinite(pid)) return {};
  try {
    const data = await getStoreProduct(storeId, pid);
    const { product, is_available: isAvailable, stock } = data.inventory;
    const indexable = isAvailable && stock > 0;
    const description = (product.description || "").slice(0, 160);
    return {
      title: `${product.name} — ${data.store.name} | ${COMPANY_NAME}`,
      description,
      robots: indexable ? undefined : { index: false },
      openGraph: {
        title: `${product.name} — ${data.store.name}`,
        description,
        type: "website",
        images: product.image_url ? [{ url: product.image_url }] : undefined,
      },
    };
  } catch {
    return {};
  }
}

export default async function ProductFullPage({ params }: { params: Params }) {
  const { locale, id, productId } = await params;
  const storeId = Number(id);
  const pid = Number(productId);
  if (!Number.isFinite(storeId) || !Number.isFinite(pid)) notFound();

  let data;
  try {
    data = await getStoreProduct(storeId, pid);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  const t = await getTranslations("Product");
  const { breadcrumb } = data;
  return (
    <main className={styles.page}>
      <nav className={styles.breadcrumb} aria-label="Breadcrumb">
        <Link href={`/${locale}/stores/${storeId}`}>{data.store.name}{data.store.is_premium && <CrownBadge />}</Link>
        <span aria-hidden> / </span>
        <span>{breadcrumb.service_name}</span>
        <span aria-hidden> / </span>
        <span>{breadcrumb.category_name}</span>
        <span aria-hidden> / </span>
        <span>{breadcrumb.subcategory_name}</span>
      </nav>
      <ProductDetail data={data} variant="page" />
      <p className={styles.backLink}>
        <Link href={`/${locale}/stores/${storeId}`}>← {t("backToStore")}</Link>
      </p>
    </main>
  );
}
