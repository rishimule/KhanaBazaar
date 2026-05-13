// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Khana Bazaar — Product Detail API
 *
 * Server-side fetch for the per-store product detail endpoint. Uses Next.js
 * data cache (60s revalidate) keyed by store+product so repeat opens within
 * the window skip the network. Stock display is advisory; checkout
 * re-validates authoritatively.
 */
import { get } from "@/lib/api";
import type { StoreProductDetail } from "@/types";

export async function getStoreProduct(
  storeId: number,
  productId: number,
): Promise<StoreProductDetail> {
  return get<StoreProductDetail>(
    `/api/v1/stores/${storeId}/products/${productId}`,
    null,
    { next: { revalidate: 60, tags: [`store-${storeId}-product-${productId}`] } },
  );
}
