// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/AuthContext";
import { listCatalog } from "@/lib/catalog";
import type { EntityKind } from "@/types";

interface Ancestors {
  service?: string;
  category?: string;
  subcategory?: string;
}

async function fetchOne(
  entity: EntityKind,
  id: number,
  token: string | null,
): Promise<string | undefined> {
  try {
    const res = await listCatalog(entity, { page_size: 100, is_active: null }, token);
    const item = res.items.find((i) => i.id === id);
    return item?.name;
  } catch {
    return undefined;
  }
}

/**
 * Resolves the human-readable name for each of (serviceId, categoryId,
 * subcategoryId). Used by the breadcrumb so URLs that look like
 * `?service=12&category=5` render "Services / Grocery / Produce" instead
 * of "Service #12 / Category #5".
 */
export function useAncestorNames(
  serviceId?: number,
  categoryId?: number,
  subcategoryId?: number,
): Ancestors {
  const { token } = useAuth();
  const [names, setNames] = useState<Ancestors>({});

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const next: Ancestors = {};
      if (serviceId) next.service = await fetchOne("service", serviceId, token);
      if (categoryId) next.category = await fetchOne("category", categoryId, token);
      if (subcategoryId)
        next.subcategory = await fetchOne("subcategory", subcategoryId, token);
      if (!cancelled) setNames(next);
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [serviceId, categoryId, subcategoryId, token]);

  return names;
}
