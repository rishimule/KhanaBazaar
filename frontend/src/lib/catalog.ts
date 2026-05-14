// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Typed client for the admin catalog API.
 *
 * Each helper takes the auth token explicitly so callers can read it from
 * AuthContext without coupling this module to React. Entity-to-URL mapping
 * lives in PATHS so call sites don't reassemble the same paths.
 */

import { del, get, post, put } from "@/lib/api";
import type {
  CatalogEntity,
  CatalogEntityWrite,
  CatalogListParams,
  EntityKind,
  PagedResponse,
  TranslationOut,
} from "@/types";

const PATHS: Record<EntityKind, string> = {
  service: "/api/v1/catalog/admin/services",
  category: "/api/v1/catalog/admin/categories",
  subcategory: "/api/v1/catalog/admin/subcategories",
  product: "/api/v1/catalog/admin/products",
};

function buildQuery(params: CatalogListParams = {}): string {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  if (params.is_active !== undefined && params.is_active !== null) {
    sp.set("is_active", String(params.is_active));
  }
  if (params.page) sp.set("page", String(params.page));
  if (params.page_size) sp.set("page_size", String(params.page_size));
  if (params.service_id) sp.set("service_id", String(params.service_id));
  if (params.category_id) sp.set("category_id", String(params.category_id));
  if (params.subcategory_id) sp.set("subcategory_id", String(params.subcategory_id));
  const qs = sp.toString();
  return qs ? `?${qs}` : "";
}

export async function listCatalog(
  entity: EntityKind,
  params: CatalogListParams = {},
  token?: string | null,
): Promise<PagedResponse<CatalogEntity>> {
  return get(`${PATHS[entity]}${buildQuery(params)}`, token);
}

export async function getCatalog(
  entity: EntityKind,
  id: number,
  token?: string | null,
): Promise<CatalogEntity> {
  return get(`${PATHS[entity]}/${id}`, token);
}

export async function createCatalog(
  entity: EntityKind,
  body: CatalogEntityWrite,
  token?: string | null,
): Promise<CatalogEntity> {
  return post(PATHS[entity], body, token);
}

export async function updateCatalog(
  entity: EntityKind,
  id: number,
  body: CatalogEntityWrite,
  token?: string | null,
): Promise<CatalogEntity> {
  return put(`${PATHS[entity]}/${id}`, body, token);
}

export async function deleteCatalog(
  entity: EntityKind,
  id: number,
  token?: string | null,
): Promise<void> {
  await del(`${PATHS[entity]}/${id}`, token);
}

export async function upsertTranslation(
  entity: EntityKind,
  id: number,
  body: TranslationOut,
  token?: string | null,
): Promise<void> {
  await post(`${PATHS[entity]}/${id}/translations`, body, token);
}
