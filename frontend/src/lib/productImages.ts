// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { ApiError, patch, post, del } from "@/lib/api";
import type { ProductImage } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Multipart upload — uses fetch directly so the browser sets the multipart
 *  boundary (the shared `post` helper forces application/json). */
export async function uploadProductImage(
  productId: number,
  file: File | Blob,
  token: string | null,
): Promise<ProductImage> {
  const form = new FormData();
  form.append("file", file, "upload.webp");
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(
    `${API_BASE}/api/v1/catalog/admin/products/${productId}/images/upload`,
    { method: "POST", headers, body: form },
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.detail ?? res.statusText, res.status);
  }
  return res.json() as Promise<ProductImage>;
}

export function addProductImageUrl(
  productId: number,
  url: string,
  token: string | null,
): Promise<ProductImage> {
  return post<ProductImage>(
    `/api/v1/catalog/admin/products/${productId}/images/url`,
    { url },
    token,
  );
}

export function reorderProductImages(
  productId: number,
  imageIds: number[],
  token: string | null,
): Promise<ProductImage[]> {
  return patch<ProductImage[]>(
    `/api/v1/catalog/admin/products/${productId}/images/order`,
    { image_ids: imageIds },
    token,
  );
}

export function deleteProductImage(
  productId: number,
  imageId: number,
  token: string | null,
): Promise<void> {
  return del<void>(
    `/api/v1/catalog/admin/products/${productId}/images/${imageId}`,
    token,
  );
}
