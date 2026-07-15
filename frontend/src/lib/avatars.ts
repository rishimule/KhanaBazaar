// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import { ApiError, del } from "@/lib/api";
import type { CustomerProfile, SellerProfileChangeRequest, Store } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function uploadMultipart<T>(
  path: string,
  file: Blob,
  token: string | null,
): Promise<T> {
  const form = new FormData();
  form.append("file", file, "avatar.webp");
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.detail ?? res.statusText, res.status);
  }
  return res.json() as Promise<T>;
}

export function uploadCustomerAvatar(
  file: Blob,
  token: string | null,
): Promise<CustomerProfile> {
  return uploadMultipart<CustomerProfile>("/api/v1/customers/me/avatar", file, token);
}

export function deleteCustomerAvatar(token: string): Promise<CustomerProfile> {
  return del<CustomerProfile>("/api/v1/customers/me/avatar", token);
}

export function uploadSellerAvatar(
  file: Blob,
  token: string | null,
): Promise<SellerProfileChangeRequest> {
  return uploadMultipart<SellerProfileChangeRequest>(
    "/api/v1/sellers/me/avatar",
    file,
    token,
  );
}

export function uploadStoreLogo(
  file: Blob,
  token: string | null,
): Promise<SellerProfileChangeRequest> {
  return uploadMultipart<SellerProfileChangeRequest>(
    "/api/v1/sellers/me/store/logo",
    file,
    token,
  );
}

/** Admin supervisor direct-apply: uploads a store logo for `sellerId` (the
 *  seller's User id) and returns the updated Store. Applies immediately. */
export function adminUploadStoreLogo(
  sellerId: number,
  file: Blob,
  token: string | null,
): Promise<Store> {
  return uploadMultipart<Store>(
    `/api/v1/admin/sellers/${sellerId}/store/logo`,
    file,
    token,
  );
}
