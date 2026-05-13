// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { ApiError } from "@/lib/api";
import { getStoreProduct } from "@/lib/api/products";
import ProductDetail from "@/components/ProductDetail/ProductDetail";
import ProductModal from "./ProductModal";

export default async function InterceptedProductPage({
  params,
}: {
  params: Promise<{ locale: string; id: string; productId: string }>;
}) {
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
  return (
    <ProductModal
      storeUrl={`/${locale}/stores/${storeId}`}
      closeLabel={t("closeModal")}
    >
      <ProductDetail data={data} variant="modal" />
    </ProductModal>
  );
}
