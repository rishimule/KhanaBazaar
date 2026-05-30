// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Frontend search client: debounce, abort, sequence-drop, in-memory cache.
 * Talks to /api/v1/search/* through the existing api.ts wrapper for headers.
 */
import { get, post, ApiError } from "./api";

export type SuggestTerm = {
  text: string;
  kind: "product_name" | "category" | "subcategory";
};

export type SuggestBestStore = {
  id: number;
  name: string;
  price: number;
  is_available: boolean;
};

export type SuggestProduct = {
  id: number;
  name: string;
  image_url: string | null;
  min_price: number;
  store_count: number;
  best_store: SuggestBestStore | null;
};

export type SuggestStoreRow = {
  id: number;
  name: string;
  service_ids: number[];
  distance_km: number | null;
};

export type SuggestResponse = {
  query_id: string;
  terms: SuggestTerm[];
  products: SuggestProduct[];
  stores: SuggestStoreRow[];
};

export type PerStoreOffer = {
  store_id: number;
  store_name: string;
  price: number;
  stock: number;
  is_available: boolean;
  is_serviceable: boolean;
  store_paused?: boolean;
  distance_km: number | null;
};

export type ProductCard = {
  id: number;
  slug: string;
  name: string;
  image_url: string | null;
  brand: string | null;
  unit: string | null;
  service_id: number;
  service_name: string | null;
  category_id: number;
  subcategory_id: number;
  min_price: number;
  max_price: number;
  in_stock_anywhere: boolean;
  per_store_offers: PerStoreOffer[];
};

export type ProductsResponse = {
  query_id: string;
  query: string;
  total: number;
  page: number;
  page_size: number;
  products: ProductCard[];
  facets: {
    service_id: Record<string, number>;
    category_id: Record<string, number>;
    min_price_bucket: Record<string, number>;
  };
  applied_filters: Record<string, number | string>;
  sort: string;
};

export type CompareOffer = {
  store: {
    id: number;
    name: string;
    lat: number | null;
    lng: number | null;
    distance_km: number | null;
    delivery_radius_km: number;
  };
  inventory_id: number;
  price: number;
  stock: number;
  is_available: boolean;
  is_serviceable: boolean;
  store_paused?: boolean;
};

export type CompareResponse = {
  product: ProductCard;
  offers: CompareOffer[];
};

// ─── Suggest with debounce + abort + cache ────────────────────────────────

type SuggestArgs = {
  q: string;
  lat?: number;
  lng?: number;
  storeId?: number;
  locale: string;
};

const GRID = 0.005;
function cell(v: number | undefined): string {
  if (v === undefined) return "x";
  return (Math.floor(v / GRID) * GRID).toFixed(4);
}

function key(a: SuggestArgs): string {
  return `${a.q.trim().toLowerCase()}|${cell(a.lat)}|${cell(a.lng)}|${a.storeId ?? 0}|${a.locale}`;
}

const cache = new Map<string, { v: SuggestResponse; t: number }>();
const TTL_MS = 60_000;
let seq = 0;
let inflightCtrl: AbortController | null = null;

export async function suggest(args: SuggestArgs): Promise<SuggestResponse | null> {
  const k = key(args);
  const cached = cache.get(k);
  if (cached && Date.now() - cached.t < TTL_MS) return cached.v;

  // Abort any prior in-flight suggest request.
  if (inflightCtrl !== null) inflightCtrl.abort();
  const ctrl = new AbortController();
  inflightCtrl = ctrl;
  const mySeq = ++seq;
  const params = new URLSearchParams({ q: args.q.trim() });
  if (args.lat !== undefined) params.set("lat", String(args.lat));
  if (args.lng !== undefined) params.set("lng", String(args.lng));
  if (args.storeId !== undefined) params.set("store_id", String(args.storeId));

  try {
    const res = await get<SuggestResponse>(`/api/v1/search/suggest?${params}`, null, {
      headers: { "Accept-Language": args.locale },
      signal: ctrl.signal,
    });
    if (mySeq !== seq) return null;
    cache.set(k, { v: res, t: Date.now() });
    return res;
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") return null;
    if (e instanceof ApiError && e.status === 429) {
      await new Promise((r) => setTimeout(r, 1000));
      return suggest(args);
    }
    if (e instanceof ApiError && e.status === 400) return null;
    throw e;
  } finally {
    if (inflightCtrl === ctrl) inflightCtrl = null;
  }
}

export type StoreHit = {
  id: number;
  name: string;
  service_ids: number[];
  distance_km: number | null;
};

export type StoresResponse = {
  total: number;
  page: number;
  page_size: number;
  stores: StoreHit[];
};

export async function searchStores(args: {
  q: string;
  lat?: number;
  lng?: number;
  page?: number;
  pageSize?: number;
}): Promise<StoresResponse> {
  const params = new URLSearchParams({ q: args.q.trim() });
  if (args.lat !== undefined) params.set("lat", String(args.lat));
  if (args.lng !== undefined) params.set("lng", String(args.lng));
  if (args.page !== undefined) params.set("page", String(args.page));
  if (args.pageSize !== undefined) params.set("page_size", String(args.pageSize));
  return get<StoresResponse>(`/api/v1/search/stores?${params}`);
}

export function logClick(payload: {
  query_id: string;
  clicked_product_id?: number;
  clicked_store_id?: number;
  position: number;
}): void {
  // sendBeacon with `application/json` is blocked by browsers as a non-simple
  // request (would require a preflight that sendBeacon can't make). Fall back
  // to a fire-and-forget fetch which sets the correct CORS-allowed content
  // type via the existing api.ts wrapper.
  post("/api/v1/search/click", payload).catch(() => undefined);
}

// ─── Results page + comparison page ──────────────────────────────────────

export type SearchProductsArgs = {
  q?: string;
  lat?: number;
  lng?: number;
  storeId?: number;
  serviceId?: number;
  categoryId?: number;
  subcategoryId?: number;
  minPrice?: number;
  maxPrice?: number;
  sort?: string;
  page?: number;
  pageSize?: number;
};

export async function searchProducts(
  args: SearchProductsArgs,
  locale: string,
): Promise<ProductsResponse> {
  const params = new URLSearchParams();
  if (args.q) params.set("q", args.q);
  if (args.lat !== undefined) params.set("lat", String(args.lat));
  if (args.lng !== undefined) params.set("lng", String(args.lng));
  if (args.storeId !== undefined) params.set("store_id", String(args.storeId));
  if (args.serviceId !== undefined) params.set("service_id", String(args.serviceId));
  if (args.categoryId !== undefined) params.set("category_id", String(args.categoryId));
  if (args.subcategoryId !== undefined)
    params.set("subcategory_id", String(args.subcategoryId));
  if (args.minPrice !== undefined) params.set("min_price", String(args.minPrice));
  if (args.maxPrice !== undefined) params.set("max_price", String(args.maxPrice));
  if (args.sort) params.set("sort", args.sort);
  if (args.page) params.set("page", String(args.page));
  if (args.pageSize) params.set("page_size", String(args.pageSize));
  return get<ProductsResponse>(`/api/v1/search/products?${params}`, null, {
    headers: { "Accept-Language": locale },
  });
}

export async function compareProduct(
  productId: number,
  args: { lat?: number; lng?: number; locale: string }
): Promise<CompareResponse> {
  const params = new URLSearchParams();
  if (args.lat !== undefined) params.set("lat", String(args.lat));
  if (args.lng !== undefined) params.set("lng", String(args.lng));
  const qs = params.toString();
  return get<CompareResponse>(
    `/api/v1/search/products/${productId}/stores${qs ? `?${qs}` : ""}`,
    null,
    { headers: { "Accept-Language": args.locale } },
  );
}

// ─── Browse (per-service category carousels) ─────────────────────────────

export type BrowseProductCard = {
  id: number;
  slug: string;
  name: string;
  image_url: string | null;
  brand: string | null;
  unit: string | null;
  min_price: number;
  max_price: number;
  in_stock_anywhere: boolean;
  category_id: number;
};

export type BrowseSubcategory = {
  id: number;
  slug: string;
  name: string;
};

export type BrowseCategory = {
  id: number;
  slug: string;
  name: string;
  subcategories: BrowseSubcategory[];
  products: BrowseProductCard[];
};

export type BrowseResponse = {
  service_id: number;
  service_name: string;
  categories: BrowseCategory[];
};

export async function browseProducts(
  args: { serviceId: number; lat?: number; lng?: number; perCategory?: number },
  locale: string,
): Promise<BrowseResponse> {
  const params = new URLSearchParams({ service_id: String(args.serviceId) });
  if (args.lat !== undefined) params.set("lat", String(args.lat));
  if (args.lng !== undefined) params.set("lng", String(args.lng));
  if (args.perCategory !== undefined)
    params.set("per_category", String(args.perCategory));
  return get<BrowseResponse>(`/api/v1/search/browse?${params}`, null, {
    headers: { "Accept-Language": locale },
  });
}
