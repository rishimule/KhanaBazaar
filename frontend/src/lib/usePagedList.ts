// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface RefetchOptions {
  /**
   * Skip the loading flag so an already-rendered list is refreshed in place
   * instead of being replaced by a spinner. Used by background refreshes
   * (focus / visibilitychange), never by a user-initiated query change.
   */
  quiet?: boolean;
}

interface UsePagedListResult<R> {
  data: R | null;
  loading: boolean;
  error: Error | null;
  refetch: (options?: RefetchOptions) => void;
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

  const refetch = useCallback((options?: RefetchOptions) => {
    const quiet = options?.quiet === true;
    const reqId = ++reqIdRef.current;
    if (!quiet) {
      setLoading(true);
      setError(null);
    }
    fetcherRef
      .current()
      .then((res) => {
        if (reqIdRef.current !== reqId) return;
        setData(res);
        if (quiet) setError(null);
      })
      .catch((e) => {
        if (reqIdRef.current !== reqId) return;
        // A failed background refresh keeps the last good page on screen.
        if (!quiet) setError(e as Error);
      })
      .finally(() => {
        if (reqIdRef.current !== reqId) return;
        // Unconditional, even for a quiet refetch: a quiet refetch can
        // supersede an in-flight loud one (tab focused mid-load), and the
        // superseded request's finally bails on the reqId guard — so skipping
        // it here would strand `loading` at true forever.
        setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [depsKey]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { data, loading, error, refetch };
}
