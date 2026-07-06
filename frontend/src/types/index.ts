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
  preferred_language: string;
  full_name?: string;
  avatar_url?: string | null;
  needs_policy_acceptance?: boolean;
}

/** A top-level service / vertical (Grocery, Electronics, Pharmacy, etc.). */
export interface Service extends BaseSchema {
  slug: string;
  name: string;
  description?: string;
  is_active: boolean;
  sort_order: number;
  free_delivery_threshold?: number;
  delivery_fee?: number;
  delivery_eta_min_minutes?: number;
  delivery_eta_max_minutes?: number;
  is_paused?: boolean;
  pause_reason?: string | null;
  paused_until?: string | null;
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

/** A single image attached to a master product (admin-managed gallery). */
export interface ProductImage {
  id?: number;
  url: string;
  source?: "uploaded" | "external";
  position: number;
}

/** A product in the master catalog managed by admins. */
export interface MasterProduct extends BaseSchema {
  name: string;
  description: string;
  category_id: number;
  subcategory_id: number;
  subcategory_name: string;
  image_url?: string;
  images?: ProductImage[];
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
  avatar_url: string | null;
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
  is_paused: boolean;
  pause_reason?: string | null;
  paused_until?: string | null;
  /** Set when the store list was queried with the user's lat/lng. */
  distance_km?: number | null;
  /** True when the store has a live paid (non-Freebie) fee arrangement. */
  is_premium?: boolean;
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
  is_premium?: boolean;
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
  free_delivery_threshold?: number;
  delivery_fee?: number;
  delivery_eta_min_minutes?: number;
  delivery_eta_max_minutes?: number;
}

/** Seller application verification states. */
export type VerificationStatus = "pending" | "approved" | "rejected";

/** Seller profile with business and compliance details. */
export interface SellerProfile extends BaseSchema {
  user_id: number;
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
  rejection_reason?: string;
  avatar_url: string | null;
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
  // Delivery-handover OTP. `otp` is populated only for the owning customer
  // while the order is dispatched; sellers/admins always receive null.
  otp?: string | null;
  otp_locked?: boolean;
  otp_attempts_remaining?: number;
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
  delivery_eta_min_minutes?: number;
  delivery_eta_max_minutes?: number;
  preferred_delivery_date?: string | null;
  preferred_delivery_window?: string | null;
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
  total: number;
  page: number;
  page_size: number;
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
  image_url: string | null;
  category_id: number;
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
  is_premium?: boolean;
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

export type OnboardingRequestStatus =
  | "new"
  | "contacted"
  | "onboarded"
  | "dismissed";

export interface SellerOnboardingRequestCreate {
  store_name: string;
  contact_phone: string;
  contact_email: string;
  contact_address: string;
  preferred_categories?: string | null;
  area_lat?: number | null;
  area_lng?: number | null;
  area_label?: string | null;
  source?: string | null;
}

export interface SellerOnboardingRequest extends SellerOnboardingRequestCreate {
  id: number;
  submitted_by_user_id: number | null;
  status: OnboardingRequestStatus;
  created_at: string;
  updated_at: string;
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
  images?: ProductImage[];
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
  store_paused?: boolean;
  active_order_count: number;
  total_product_count: number;
  services: Service[];
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

// --- Seller profile change requests ---

export type SellerProfileChangeGroup =
  | "identity"
  | "address"
  | "legal"
  | "banking"
  | "services"
  | "store_basics"
  | "avatar";

export type SellerProfileChangeStatus =
  | "submitted"
  | "changes_requested"
  | "approved"
  | "rejected"
  | "withdrawn";

export type SellerProfileChangeEventKind =
  | "submitted"
  | "resubmitted"
  | "changes_requested"
  | "approved"
  | "approved_with_edits"
  | "rejected"
  | "withdrawn";

export interface SellerProfileChangeRequestEvent {
  id: string;
  kind: SellerProfileChangeEventKind;
  actor_user_id: number;
  actor_role: "customer" | "seller" | "admin";
  payload_json: Record<string, unknown> | null;
  note: string | null;
  created_at: string;
}

export interface SellerProfileChangeRequest {
  id: string;
  seller_profile_id: number;
  group: SellerProfileChangeGroup;
  status: SellerProfileChangeStatus;
  proposed_json: Record<string, unknown>;
  applied_json: Record<string, unknown> | null;
  baseline_json: Record<string, unknown>;
  admin_note: string | null;
  submission_count: number;
  created_at: string;
  updated_at: string;
  decided_at: string | null;
  decided_by_user_id: number | null;
  events: SellerProfileChangeRequestEvent[];
}


export interface OrderStatusCounts {
  delivered: number;
  packed: number;
  dispatched: number;
  pending: number;
  cancelled: number;
}

export interface InventoryServiceStat {
  service_id: number;
  service_name: string;
  in_stock: number;
  total: number;
}

export interface TopSubcategory {
  name: string;
  count: number;
}

export interface SellerMetrics {
  active_orders: number;
  orders_today: number;
  orders_this_month: number;
  revenue_this_month: number;
  revenue_last_month: number;
  revenue_trend_pct: number;
  total_products: number;
  out_of_stock: number;
  unavailable: number;
  store_active: boolean;
  store_paused: boolean;
  is_premium: boolean;
  pin_confirmed: boolean;
  store_name: string;
  order_status_counts: OrderStatusCounts;
  inventory_by_service: InventoryServiceStat[];
  top_subcategory: TopSubcategory | null;
}

export interface RevenueSeriesPoint {
  date: string;
  gov: number;
}

export interface RevenueSeries {
  points: RevenueSeriesPoint[];
  avg_per_day: number;
  peak: number;
}

export interface OrderServiceStat {
  service_id: number;
  service_name: string;
  count: number;
}

export interface AdminMetrics {
  active_orders: number;
  orders_today: number;
  orders_this_month: number;
  gmv_this_month: number;
  gmv_last_month: number;
  gmv_trend_pct: number;
  active_master_products: number;
  active_categories: number;
  active_stores: number;
  pending_applications: number;
  approved_sellers: number;
  rejected_sellers: number;
  open_change_requests: number;
  orders_by_service: OrderServiceStat[];
}
