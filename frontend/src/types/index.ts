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
  items: OrderItem[];
  payment: OrderPayment;
  delivery: OrderDelivery;
}

export interface OrderListResponse {
  orders: Order[];
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
