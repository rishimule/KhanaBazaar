// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Khana Bazaar API wire types.
 *
 * These interfaces match the public FastAPI response/request shapes used by
 * the frontend. They are intentionally not exact database table models because
 * the backend composes compatibility fields such as full_name, seller_id,
 * category name, product name, and base_price from the reset baseline schema.
 */

/** User roles matching backend RBAC enum. */
export type UserRole = "admin" | "seller" | "customer";

/** Base fields present on all backend models. */
export interface BaseSchema {
  id: number;
  created_at: string;
  updated_at: string;
}

/** User model matching backend User(BaseSchema, UserBase). */
export interface User extends BaseSchema {
  email: string;
  is_active: boolean;
  role: UserRole;
  full_name?: string;
}

/** A top-level service / vertical (Grocery, Electronics, Pharmacy, etc.). */
export interface Service extends BaseSchema {
  slug: string;
  name: string;
  description?: string;
  is_active: boolean;
  sort_order: number;
}

/** Category from the master catalog. */
export interface Category extends BaseSchema {
  name: string;
  description?: string;
  service_id: number;
}

/** Subcategory under a Category in the master catalog. */
export interface Subcategory extends BaseSchema {
  name: string;
  description?: string;
  category_id: number;
  slug: string;
}

/** A product in the master catalog managed by admins. */
export interface MasterProduct extends BaseSchema {
  name: string;
  description: string;
  category_id: number;
  subcategory_id: number;
  subcategory_name: string;
  image_url?: string;
  base_price: number;
}

/** How the lat/lng on an address was acquired (used by backend confidence
 *  scoring + telemetry; safe to omit on writes). */
export type LocationSource = "manual" | "autocomplete" | "pin" | "geocoded";

/** Structured address matching backend AddressPayload. */
export interface Address {
  address_line1: string;
  address_line2: string | null;
  landmark: string | null;
  city: string;
  state: string;
  pincode: string;
  country: string;
  latitude: number | null;
  longitude: number | null;
  digipin?: string | null;
  place_id?: string | null;
  location_source?: LocationSource | null;
}

/** A saved delivery address for a customer account. */
export interface CustomerAddress {
  id: number;
  label: string | null;
  is_default: boolean;
  address: Address;
}

/** Customer profile payload returned by GET /customers/me. */
export interface CustomerProfile {
  user_id: number;
  email: string;
  first_name: string;
  last_name: string | null;
  phone: string | null;
  date_of_birth: string | null;
  preferred_language: string | null;
  marketing_opt_in: boolean;
  notify_order_email: boolean;
  notify_order_sms: boolean;
  phone_verified_at: string | null;
  addresses: CustomerAddress[];
}

/** A seller's store on the platform. */
export interface Store extends BaseSchema {
  name: string;
  address: Address;
  is_active: boolean;
  seller_id: number;
  services: Service[];
  delivery_radius_km: number;
  pin_confirmed: boolean;
  /** Set when the store list was queried with the user's lat/lng. */
  distance_km?: number | null;
}

/** A store-specific inventory entry linking a product to a store. */
export interface StoreInventory extends BaseSchema {
  store_id: number;
  product_id: number;
  price: number;
  stock: number;
  is_available: boolean;
}

/** Enriched inventory item with product details for display. */
export interface InventoryWithProduct extends StoreInventory {
  product: MasterProduct;
}

/** Lightweight store summary returned by the product detail endpoint. */
export interface StoreSummary {
  id: number;
  name: string;
}

/** Lightweight service summary returned by the product detail endpoint. */
export interface ServiceLite {
  id: number;
  name: string;
}

/** Localized breadcrumb returned alongside the product detail payload. */
export interface StoreProductBreadcrumb {
  service_id: number;
  service_name: string;
  category_id: number;
  category_name: string;
  subcategory_id: number;
  subcategory_name: string;
}

/** Full payload from GET /api/v1/stores/{store_id}/products/{product_id}. */
export interface StoreProductDetail {
  store: StoreSummary;
  service: ServiceLite;
  inventory: InventoryWithProduct;
  breadcrumb: StoreProductBreadcrumb;
}

/* ------------------------------------------------------------------
 * Storefront tree (server-aggregated; see GET /stores/{id}/storefront).
 * Flat lists were retired in favour of this shape so the store-detail
 * page can render in one round trip instead of joining four catalog
 * fetches client-side.
 * ------------------------------------------------------------------ */

export interface StorefrontItem {
  inventory_id: number;
  product_id: number;
  product_slug: string;
  product_name: string;
  image_url: string | null;
  description: string | null;
  price: number;
  stock: number;
}

export interface StorefrontSubcategory {
  id: number;
  slug: string;
  name: string;
  sort_order: number;
  items: StorefrontItem[];
}

export interface StorefrontCategory {
  id: number;
  slug: string;
  name: string;
  sort_order: number;
  subcategories: StorefrontSubcategory[];
}

export interface StorefrontService {
  id: number;
  slug: string;
  name: string;
  sort_order: number;
  categories: StorefrontCategory[];
}

export interface StorefrontResponse {
  store: Store;
  services: StorefrontService[];
}

/** A single item within a shopping cart. */
export interface CartItem {
  product_id: number;
  inventory_id: number;
  product_name: string;
  quantity: number;
  price: number;
  image_url?: string;
  id?: number;
}

/** A shopping cart sub-basket scoped to one (store, service) pair. */
export interface Cart {
  store_id: number;
  store_name: string;
  service_id: number;
  service_name: string;
  items: CartItem[];
}

/** Seller application verification states. */
export type VerificationStatus = "pending" | "approved" | "rejected";

/** Seller profile with business and compliance details. */
export interface SellerProfile extends BaseSchema {
  user_id: number;
  business_name: string;
  services: Service[];
  address: Address;
  phone: string;
  gst_number: string | null;
  fssai_license: string | null;
  bank_account_number: string | null;
  bank_ifsc: string | null;
  verification_status: VerificationStatus;
  rejection_reason?: string;
}

/** A seller application as returned by GET /sellers/admin/applications. */
export interface SellerApplication {
  seller_id: number;
  email: string;
  full_name: string;
  business_name: string;
  services: Service[];
  address: Address;
  phone: string;
  gst_number: string | null;
  fssai_license: string | null;
  bank_account_number: string | null;
  bank_ifsc: string | null;
  verification_status: VerificationStatus;
  rejection_reason: string | null;
  submitted_at: string;
  updated_at: string;
}

/** Per-status counts for the admin applications dashboard. */
export interface ApplicationCounts {
  pending: number;
  approved: number;
  rejected: number;
  total: number;
}

export type OrderStatus = "pending" | "packed" | "dispatched" | "delivered" | "cancelled";
export type PaymentStatus = "pending" | "paid" | "failed" | "refunded";
export type DeliveryStatus = "pending" | "packed" | "dispatched" | "delivered" | "cancelled";
export type PaymentMethod = "cash" | "upi";

export interface OrderItem {
  id: number;
  inventory_id: number | null;
  product_name_snapshot: string;
  unit_price_snapshot: number;
  quantity: number;
  line_total: number;
}

export interface OrderPayment {
  method: PaymentMethod;
  status: PaymentStatus;
  amount: number;
  paid_at: string | null;
}

export interface OrderDelivery {
  status: DeliveryStatus;
  packed_at: string | null;
  dispatched_at: string | null;
  delivered_at: string | null;
}

export interface OrderReview {
  rating: number;
  comment: string | null;
}

export interface Order {
  id: number;
  store_id: number;
  store_name: string;
  service_id: number;
  service_name: string;
  customer_name?: string | null;
  status: OrderStatus;
  subtotal: number;
  delivery_fee: number;
  tax: number;
  total: number;
  placed_at: string;
  delivery_address_snapshot: string;
  store_latitude: number | null;
  store_longitude: number | null;
  delivery_latitude: number | null;
  delivery_longitude: number | null;
  items: OrderItem[];
  payment: OrderPayment;
  delivery: OrderDelivery;
  review: OrderReview | null;
}

export interface OrderListResponse {
  orders: Order[];
}

export interface OrderNotification {
  id: number;
  order_id: number | null;
  type: string;
  title: string;
  body: string;
  status_value: string;
  read: boolean;
  created_at: string;
}

export interface NotificationListResponse {
  notifications: OrderNotification[];
  unread_count: number;
}

export interface CustomerOrderSummary {
  id: number;
  store_id: number;
  store_name: string;
  service_id: number;
  service_name: string;
  total: number;
  placed_at: string;
}

export interface CustomerStats {
  orders_this_month: number;
  lifetime_spend: number;
  most_ordered_store_id: number | null;
  most_ordered_store_name: string | null;
  recent_delivered: CustomerOrderSummary[];
}

export interface EligibleProduct {
  id: number;
  name: string;
  base_price: number;
  subcategory_id: number;
  subcategory_name: string;
  category_id: number;
  category_name: string;
  service_id: number;
  service_name: string;
  in_inventory: boolean;
}

export interface BulkInventoryItem {
  product_id: number;
  price: number;
  stock: number;
  is_available: boolean;
}

export type BulkInventoryErrorCode =
  | "PRICE_INVALID"
  | "STOCK_INVALID"
  | "PRODUCT_NOT_FOUND"
  | "SERVICE_NOT_APPROVED"
  | "DUPLICATE_PRODUCT"
  | "ROW_LIMIT";

export interface BulkInventoryError {
  index: number;
  product_id: number;
  code: BulkInventoryErrorCode;
  message: string;
}

// ---------------------------------------------------------------------------
// Price comparison
// ---------------------------------------------------------------------------

export interface ComparisonItem {
  product_id: number;
  product_name: string;
  quantity: number;
  inventory_id: number | null;
  unit_price: number;
  is_available: boolean;
  stock: number;
  line_total: number;
  imputed: boolean;
}

export interface ComparisonAlternative {
  id: number;
  name: string;
  distance_km: number;
  covered_count: number;
  missing_count: number;
  covered_subtotal: number;
  imputed_subtotal: number;
  effective_total: number;
  items: ComparisonItem[];
}

export interface CompareResponse {
  alternatives: ComparisonAlternative[];
}

export type ReplaceAdjustmentReason =
  | "stock_capped"
  | "stock_exhausted"
  | "item_unavailable";

export interface ReplaceAdjustment {
  inventory_id: number;
  requested_quantity: number;
  granted_quantity: number;
  reason: ReplaceAdjustmentReason;
}

export interface ReplaceResponse {
  cart: Cart;
  adjustments: ReplaceAdjustment[];
}

export interface ResolvedReorderItem {
  product_id: number;
  inventory_id: number;
  product_name: string;
  image_url?: string | null;
  unit_price: number;
  quantity: number;
}

export interface ReorderResolveResponse {
  store_id: number;
  store_name: string;
  service_id: number;
  service_name: string;
  items: ResolvedReorderItem[];
  adjustments: ReplaceAdjustment[];
}

// ─── Admin catalog ─────────────────────────────────────────────

export type EntityKind = "service" | "category" | "subcategory" | "product";

export interface PagedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface TranslationOut {
  language_code: string;
  name: string;
  description: string | null;
}

export interface CatalogEntity {
  id: number;
  created_at: string;
  updated_at: string;
  name: string;
  slug: string;
  description: string | null;
  image_url: string | null;
  is_active: boolean;
  sort_order?: number;
  child_count?: number;
  translations: TranslationOut[];
  // entity-specific fields
  service_id?: number;
  category_id?: number;
  subcategory_id?: number;
  base_price?: number;
  brand?: string | null;
  unit?: string | null;
}

export interface CatalogListParams {
  q?: string;
  is_active?: boolean | null;
  page?: number;
  page_size?: number;
  service_id?: number;
  category_id?: number;
  subcategory_id?: number;
}

export interface CatalogEntityWrite {
  name?: string;
  slug?: string;
  description?: string | null;
  image_url?: string | null;
  sort_order?: number;
  is_active?: boolean;
  service_id?: number;
  category_id?: number;
  subcategory_id?: number;
  base_price?: number;
  brand?: string | null;
  unit?: string | null;
}

// ---------------------------------------------------------------------------
// Admin supervisor (see backend/app/src/app/api/admin_actions.py).
// ---------------------------------------------------------------------------

export interface AdminActionLog {
  id: string;
  admin_user_id: number;
  admin_email: string;
  target_seller_id: number;
  target_type: "inventory" | "order" | "store" | "seller_profile";
  target_id: number;
  action: string;
  before_json: Record<string, unknown> | null;
  after_json: Record<string, unknown> | null;
  reason: string | null;
  created_at: string;
}

export interface AdminActivityPage {
  items: AdminActionLog[];
  next_cursor: string | null;
}

export interface SellerHubSummary {
  seller_id: number;
  business_name: string;
  verification_status: "pending" | "approved" | "rejected";
  email: string;
  store_id: number | null;
  active_order_count: number;
  total_product_count: number;
}

export interface AdminInventoryRow {
  id: number;
  store_id: number;
  product_id: number;
  product_name: string;
  product_brand: string | null;
  product_unit: string | null;
  price: number;
  stock: number;
  is_available: boolean;
}

// ---------------------------------------------------------------------------
// Favourites
// ---------------------------------------------------------------------------

export interface FavoriteIdsResponse {
  ids: number[];
}

export interface FavoriteProductPreview {
  product_id: number;
  name: string;
  image_url: string | null;
  category_id: number;
}

export interface FavoriteAtStore {
  product_id: number;
  name: string;
  image_url: string | null;
  category_id: number;
  service_id: number;
  service_name: string;
  inventory_id: number;
  price: number;
  stock: number;
  favourited_at: string;
}

export interface StoreFavGroup {
  store_id: number;
  store_name: string;
  distance_km: number;
  items: FavoriteAtStore[];
}

export interface FavoritesGroupedResponse {
  groups: StoreFavGroup[];
  unavailable: FavoriteProductPreview[];
}

export interface FavoriteToggleResponse {
  favourited: boolean;
}

