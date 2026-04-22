/**
 * Khana Bazaar — Mock Data
 *
 * Realistic Indian grocery store data for frontend development.
 * This will be replaced with real API calls in Phase 4.
 */

import { Category, MasterProduct, Store, InventoryWithProduct } from "@/types";

// ─── Categories ──────────────────────────────────────────────

export const mockCategories: Category[] = [
  {
    id: 1,
    name: "Fruits & Vegetables",
    description: "Fresh produce from local farms",
    created_at: "2026-01-15T10:00:00Z",
    updated_at: "2026-01-15T10:00:00Z",
  },
  {
    id: 2,
    name: "Dairy & Bakery",
    description: "Milk, paneer, bread, and baked goods",
    created_at: "2026-01-15T10:00:00Z",
    updated_at: "2026-01-15T10:00:00Z",
  },
  {
    id: 3,
    name: "Staples & Grains",
    description: "Rice, atta, dal, and cooking essentials",
    created_at: "2026-01-15T10:00:00Z",
    updated_at: "2026-01-15T10:00:00Z",
  },
  {
    id: 4,
    name: "Snacks & Beverages",
    description: "Chips, biscuits, tea, coffee, and cold drinks",
    created_at: "2026-01-15T10:00:00Z",
    updated_at: "2026-01-15T10:00:00Z",
  },
];

// ─── Master Products ─────────────────────────────────────────

export const mockProducts: MasterProduct[] = [
  {
    id: 1, name: "Fresh Tomatoes", description: "Firm, red tomatoes — perfect for curries and chutneys",
    category_id: 1, image_url: "/images/products/tomatoes.jpg", base_price: 40,
    created_at: "2026-01-20T08:00:00Z", updated_at: "2026-01-20T08:00:00Z",
  },
  {
    id: 2, name: "Green Coriander Bunch", description: "Fresh dhania for garnishing and chutney",
    category_id: 1, image_url: "/images/products/coriander.jpg", base_price: 15,
    created_at: "2026-01-20T08:00:00Z", updated_at: "2026-01-20T08:00:00Z",
  },
  {
    id: 3, name: "Onions (Pyaaz)", description: "Medium-sized onions, a kitchen staple",
    category_id: 1, image_url: "/images/products/onions.jpg", base_price: 35,
    created_at: "2026-01-20T08:00:00Z", updated_at: "2026-01-20T08:00:00Z",
  },
  {
    id: 4, name: "Amul Taza Milk (1L)", description: "Toned milk, pasteurized & homogenized",
    category_id: 2, image_url: "/images/products/milk.jpg", base_price: 54,
    created_at: "2026-01-20T08:00:00Z", updated_at: "2026-01-20T08:00:00Z",
  },
  {
    id: 5, name: "Amul Paneer (200g)", description: "Fresh cottage cheese block for sabzi & tikka",
    category_id: 2, image_url: "/images/products/paneer.jpg", base_price: 90,
    created_at: "2026-01-20T08:00:00Z", updated_at: "2026-01-20T08:00:00Z",
  },
  {
    id: 6, name: "Britannia Bread (400g)", description: "Soft white sandwich bread",
    category_id: 2, image_url: "/images/products/bread.jpg", base_price: 45,
    created_at: "2026-01-20T08:00:00Z", updated_at: "2026-01-20T08:00:00Z",
  },
  {
    id: 7, name: "Toor Dal (1kg)", description: "Premium quality arhar dal for everyday cooking",
    category_id: 3, image_url: "/images/products/toor-dal.jpg", base_price: 160,
    created_at: "2026-01-20T08:00:00Z", updated_at: "2026-01-20T08:00:00Z",
  },
  {
    id: 8, name: "Basmati Rice (5kg)", description: "Long grain aged basmati — perfect for biryani",
    category_id: 3, image_url: "/images/products/rice.jpg", base_price: 450,
    created_at: "2026-01-20T08:00:00Z", updated_at: "2026-01-20T08:00:00Z",
  },
  {
    id: 9, name: "Aashirvaad Atta (5kg)", description: "Whole wheat flour for soft rotis",
    category_id: 3, image_url: "/images/products/atta.jpg", base_price: 280,
    created_at: "2026-01-20T08:00:00Z", updated_at: "2026-01-20T08:00:00Z",
  },
  {
    id: 10, name: "Lay's Classic Salted (52g)", description: "Crispy potato chips, classic flavor",
    category_id: 4, image_url: "/images/products/lays.jpg", base_price: 20,
    created_at: "2026-01-20T08:00:00Z", updated_at: "2026-01-20T08:00:00Z",
  },
  {
    id: 11, name: "Tata Tea Gold (500g)", description: "Premium blend of Assam & Darjeeling tea",
    category_id: 4, image_url: "/images/products/tea.jpg", base_price: 270,
    created_at: "2026-01-20T08:00:00Z", updated_at: "2026-01-20T08:00:00Z",
  },
  {
    id: 12, name: "Parle-G Biscuits (800g)", description: "India's iconic glucose biscuits — since 1939",
    category_id: 4, image_url: "/images/products/parle-g.jpg", base_price: 80,
    created_at: "2026-01-20T08:00:00Z", updated_at: "2026-01-20T08:00:00Z",
  },
];

// ─── Stores ──────────────────────────────────────────────────

export const mockStores: Store[] = [
  {
    id: 1,
    name: "Sharma General Store",
    address: {
      address_line1: "12, MG Road",
      address_line2: "Sector 14",
      landmark: null,
      city: "Gurugram",
      state: "Haryana",
      pincode: "122001",
      country: "India",
      latitude: null,
      longitude: null,
    },
    is_active: true,
    seller_id: 1,
    created_at: "2026-02-01T06:00:00Z",
    updated_at: "2026-02-01T06:00:00Z",
  },
  {
    id: 2,
    name: "Krishna Supermart",
    address: {
      address_line1: "45, Nehru Nagar",
      address_line2: "Andheri West",
      landmark: null,
      city: "Mumbai",
      state: "Maharashtra",
      pincode: "400058",
      country: "India",
      latitude: null,
      longitude: null,
    },
    is_active: true,
    seller_id: 2,
    created_at: "2026-02-05T06:00:00Z",
    updated_at: "2026-02-05T06:00:00Z",
  },
  {
    id: 3,
    name: "Balaji Fresh Market",
    address: {
      address_line1: "78, Rajaji Street",
      address_line2: "T. Nagar",
      landmark: null,
      city: "Chennai",
      state: "Tamil Nadu",
      pincode: "600017",
      country: "India",
      latitude: null,
      longitude: null,
    },
    is_active: true,
    seller_id: 3,
    created_at: "2026-02-10T06:00:00Z",
    updated_at: "2026-02-10T06:00:00Z",
  },
];

// ─── Store Inventories (enriched with product data) ──────────

function makeInventory(
  id: number, storeId: number, productId: number,
  price: number, stock: number
): InventoryWithProduct {
  const product = mockProducts.find((p) => p.id === productId)!;
  return {
    id, store_id: storeId, product_id: productId,
    price, stock, is_available: stock > 0,
    product,
    created_at: "2026-02-15T08:00:00Z", updated_at: "2026-02-15T08:00:00Z",
  };
}

export const mockInventories: Record<number, InventoryWithProduct[]> = {
  // Sharma General Store — has almost everything
  1: [
    makeInventory(1,  1, 1,  42,  50),
    makeInventory(2,  1, 2,  18,  30),
    makeInventory(3,  1, 3,  38,  60),
    makeInventory(4,  1, 4,  56,  20),
    makeInventory(5,  1, 5,  95,  15),
    makeInventory(6,  1, 7, 165,  25),
    makeInventory(7,  1, 8, 460,  10),
    makeInventory(8,  1, 9, 285,  12),
    makeInventory(9,  1, 10, 20, 100),
    makeInventory(10, 1, 11,275,  18),
    makeInventory(11, 1, 12, 82,  40),
  ],
  // Krishna Supermart — dairy-heavy
  2: [
    makeInventory(12, 2, 1,  45,  40),
    makeInventory(13, 2, 4,  54,  35),
    makeInventory(14, 2, 5,  92,  20),
    makeInventory(15, 2, 6,  48,  25),
    makeInventory(16, 2, 7, 158,  30),
    makeInventory(17, 2, 10, 20,  60),
    makeInventory(18, 2, 11,268,  15),
    makeInventory(19, 2, 12, 78,  50),
  ],
  // Balaji Fresh Market — produce-focused
  3: [
    makeInventory(20, 3, 1,  38,  80),
    makeInventory(21, 3, 2,  12,  50),
    makeInventory(22, 3, 3,  32,  70),
    makeInventory(23, 3, 4,  55,  15),
    makeInventory(24, 3, 8, 440,   8),
    makeInventory(25, 3, 9, 278,  10),
    makeInventory(26, 3, 11,272,  12),
  ],
};

// ─── Helper to get a store's item count ──────────────────────

export function getStoreItemCount(storeId: number): number {
  return mockInventories[storeId]?.length ?? 0;
}

/** Get a category name by ID. */
export function getCategoryName(categoryId: number): string {
  return mockCategories.find((c) => c.id === categoryId)?.name ?? "Other";
}
