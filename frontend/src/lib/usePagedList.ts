// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface UsePagedListResult<R> {
  data: R | null;
  loading: boolean;
  error: Error | null;
  refetch: () => void;
}

/**
 * Generic paginated-fetch hook. `fetcher` is invoked whenever the serialized
 * `deps` change; out-of-order responses are dropped via a request-id ref so
 * the latest query always wins. `data` is the raw response (e.g. a
 * PagedResponse<T> or an extended OrderListResponse).
 */
export function usePagedList<R>(
  fetcher: () => Promise<R>,
  deps: unknown,
): UsePagedListResult<R> {
  const [data, setData] = useState<R | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const reqIdRef = useRef(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const depsKey = JSON.stringify(deps);

  const refetch = useCallback(() => {
    const reqId = ++reqIdRef.current;
    setLoading(true);
    setError(null);
    fetcherRef
      .current()
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
  }, [depsKey]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { data, loading, error, refetch };
}
