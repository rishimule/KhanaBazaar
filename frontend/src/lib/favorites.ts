// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import type { FavoriteAtStore, InventoryWithProduct } from "@/types";

/** Adapt a backend FavoriteAtStore row into the InventoryWithProduct shape
 *  that <ProductCard> consumes. Used by /account/favorites and the
 *  store-detail favourites rail. */
export function favoriteToInventoryItem(
  it: FavoriteAtStore,
  storeId: number,
): InventoryWithProduct {
  return {
    id: it.inventory_id,
    store_id: storeId,
    product_id: it.product_id,
    price: it.price,
    stock: it.stock,
    is_available: it.stock > 0,
    created_at: it.favourited_at,
    updated_at: it.favourited_at,
    product: {
      id: it.product_id,
      name: it.name,
      description: "",
      category_id: it.category_id,
      subcategory_id: 0,
      subcategory_name: "",
      image_url: it.image_url ?? undefined,
      base_price: it.price,
      created_at: it.favourited_at,
      updated_at: it.favourited_at,
    },
  };
}
