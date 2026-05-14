// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/AuthContext";
import { listCatalog } from "@/lib/catalog";
import type {
  CatalogEntity,
  CatalogListParams,
  EntityKind,
  PagedResponse,
} from "@/types";

interface UseCatalogListResult {
  data: PagedResponse<CatalogEntity> | null;
  loading: boolean;
  error: Error | null;
  refetch: () => void;
}

/**
 * Fetches a paginated catalog list and re-fetches when the params change.
 *
 * `params` is serialized into the dependency key so the caller can pass a
 * freshly-built object on every render without retriggering needlessly.
 */
export function useCatalogList(
  entity: EntityKind,
  params: CatalogListParams,
): UseCatalogListResult {
  const { token } = useAuth();
  const [data, setData] = useState<PagedResponse<CatalogEntity> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const paramsKey = JSON.stringify(params);
  const reqIdRef = useRef(0);

  const refetch = useCallback(() => {
    const reqId = ++reqIdRef.current;
    setLoading(true);
    setError(null);
    listCatalog(entity, params, token)
      .then((res) => {
        if (reqIdRef.current !== reqId) return;
        setData(res);
      })
      .catch((e) => {
        if (reqIdRef.current !== reqId) return;
        setError(e as Error);
      })
      .finally(() => {
        if (reqIdRef.current !== reqId) return;
        setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entity, paramsKey, token]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { data, loading, error, refetch };
}
