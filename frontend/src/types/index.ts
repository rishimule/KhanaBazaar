/**
 * Khana Bazaar — Shared TypeScript Types
 *
 * These interfaces mirror the backend SQLModel schemas exactly.
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

/** Category from the master catalog. */
export interface Category extends BaseSchema {
  name: string;
  description?: string;
}

/** A product in the master catalog managed by admins. */
export interface MasterProduct extends BaseSchema {
  name: string;
  description: string;
  category_id: number;
  image_url?: string;
  base_price: number;
}

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
}

/** A seller's store on the platform. */
export interface Store extends BaseSchema {
  name: string;
  address: Address;
  is_active: boolean;
  seller_id: number;
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
  product_name: string;
  quantity: number;
  price: number;
  image_url?: string;
}

/** A shopping cart tied to a specific store. */
export interface Cart {
  store_id: number;
  store_name: string;
  items: CartItem[];
}

/** Seller application verification states. */
export type VerificationStatus = "pending" | "approved" | "rejected";

/** Seller profile with business and compliance details. */
export interface SellerProfile extends BaseSchema {
  user_id: number;
  business_name: string;
  business_category: string;
  address: Address;
  phone: string;
  gst_number: string;
  fssai_license: string;
  bank_account_number: string;
  bank_ifsc: string;
  verification_status: VerificationStatus;
  rejection_reason?: string;
}

/** A seller application as returned by GET /sellers/admin/applications. */
export interface SellerApplication {
  seller_id: number;
  email: string;
  full_name: string;
  business_name: string;
  business_category: string;
  address: Address;
  phone: string;
  gst_number: string;
  fssai_license: string;
  bank_account_number: string;
  bank_ifsc: string;
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
