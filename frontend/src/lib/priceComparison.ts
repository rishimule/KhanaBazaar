// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { get, post } from "@/lib/api";
import type { CompareResponse, ReplaceResponse } from "@/types";

export interface ReplaceItem {
  inventory_id: number;
  quantity: number;
}

export async function fetchCompare(
  token: string,
  storeId: number,
  serviceId: number,
  customerAddressId: number,
  signal: AbortSignal,
): Promise<CompareResponse> {
  return get<CompareResponse>(
    `/api/v1/carts/${storeId}/${serviceId}/compare?customer_address_id=${customerAddressId}`,
    token,
    { signal },
  );
}

export async function replaceSubBasket(
  token: string,
  storeId: number,
  serviceId: number,
  items: ReplaceItem[],
  source?: { storeId: number; inventoryIds: number[] },
): Promise<ReplaceResponse> {
  return post<ReplaceResponse>(
    `/api/v1/carts/${storeId}/${serviceId}/replace`,
    {
      items,
      ...(source
        ? {
            source_store_id: source.storeId,
            source_inventory_ids: source.inventoryIds,
          }
        : {}),
    },
    token,
  );
}
