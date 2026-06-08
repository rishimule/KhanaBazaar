// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { del, get, patch, post } from "@/lib/api";
import type { Cart, CartItem } from "@/types";

interface RemoteCartItem {
  id: number;
  inventory_id: number;
  product_id: number;
  product_name: string;
  unit_price: number;
  quantity: number;
  line_total: number;
}

interface RemoteCart {
  store_id: number;
  store_name: string;
  service_id: number;
  service_name: string;
  items: RemoteCartItem[];
  subtotal: number;
  free_delivery_threshold: number;
  delivery_fee: number;
  delivery_eta_min_minutes: number;
  delivery_eta_max_minutes: number;
}

interface RemoteCartListResponse {
  carts: RemoteCart[];
}

interface RemoteCartSyncResponse {
  carts: RemoteCart[];
  dropped: { inventory_id: number; reason: string }[];
}

function toCart(remote: RemoteCart): Cart {
  return {
    store_id: remote.store_id,
    store_name: remote.store_name,
    service_id: remote.service_id,
    service_name: remote.service_name,
    free_delivery_threshold: remote.free_delivery_threshold,
    delivery_fee: remote.delivery_fee,
    delivery_eta_min_minutes: remote.delivery_eta_min_minutes,
    delivery_eta_max_minutes: remote.delivery_eta_max_minutes,
    items: remote.items.map<CartItem>((item) => ({
      id: item.id,
      product_id: item.product_id,
      inventory_id: item.inventory_id,
      product_name: item.product_name,
      quantity: item.quantity,
      price: item.unit_price,
    })),
  };
}

export async function listCarts(token: string): Promise<Cart[]> {
  const data = await get<RemoteCartListResponse>("/api/v1/carts", token);
  return data.carts.map(toCart);
}

export async function addItem(
  token: string,
  storeId: number,
  serviceId: number,
  inventoryId: number,
  quantity: number,
): Promise<RemoteCartItem> {
  return post<RemoteCartItem>(
    "/api/v1/carts/items",
    {
      store_id: storeId,
      service_id: serviceId,
      inventory_id: inventoryId,
      quantity,
    },
    token,
  );
}

export async function updateItemQty(
  token: string,
  itemId: number,
  quantity: number,
): Promise<RemoteCartItem> {
  return patch<RemoteCartItem>(
    `/api/v1/carts/items/${itemId}`,
    { quantity },
    token,
  );
}

export async function removeItem(token: string, itemId: number): Promise<void> {
  await del<void>(`/api/v1/carts/items/${itemId}`, token);
}

export async function clearSubBasket(
  token: string,
  storeId: number,
  serviceId: number,
): Promise<void> {
  await del<void>(`/api/v1/carts/${storeId}/${serviceId}`, token);
}

export async function syncCarts(
  token: string,
  carts: {
    store_id: number;
    service_id: number;
    items: { inventory_id: number; quantity: number }[];
  }[],
): Promise<{
  carts: Cart[];
  dropped: { inventory_id: number; reason: string }[];
}> {
  const data = await post<RemoteCartSyncResponse>(
    "/api/v1/carts/sync",
    { carts },
    token,
  );
  return { carts: data.carts.map(toCart), dropped: data.dropped };
}
