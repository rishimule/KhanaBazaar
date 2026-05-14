// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/AuthContext";
import { getCatalog } from "@/lib/catalog";
import type { EntityKind } from "@/types";

interface Ancestors {
  service?: string;
  category?: string;
  subcategory?: string;
}

async function fetchName(
  entity: EntityKind,
  id: number,
  token: string | null,
): Promise<string | undefined> {
  try {
    const item = await getCatalog(entity, id, token);
    return item.name;
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
      if (serviceId) next.service = await fetchName("service", serviceId, token);
      if (categoryId) next.category = await fetchName("category", categoryId, token);
      if (subcategoryId)
        next.subcategory = await fetchName("subcategory", subcategoryId, token);
      if (!cancelled) setNames(next);
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [serviceId, categoryId, subcategoryId, token]);

  return names;
}
