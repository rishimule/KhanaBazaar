// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface RefetchOptions {
  /**
   * Skip the loading flag so already-rendered content is refreshed in place
   * instead of being replaced by a spinner. Used by background refreshes,
   * never by a user-initiated change.
   */
  quiet?: boolean;
}

export interface UseResourceResult<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  refetch: (options?: RefetchOptions) => void;
}

/**
 * Single-fetch sibling of `usePagedList`, with the same
 * `{data, loading, error, refetch}` contract.
 *
 * It exists so no seller screen has to choose between "swallow the error" and
 * "hand-roll a fourth copy of this state machine". The rule it enforces:
 * a failed fetch leaves `data` null and sets `error`, so the caller can never
 * accidentally render a zero or an empty list as though it were the truth.
 *
 * Pass `fetcher = null` when prerequisites are not ready yet (e.g. no auth
 * token). That is *not* an error and not an empty result — it stays `loading`.
 */
export function useResource<T>(
  fetcher: (() => Promise<T>) | null,
  deps: unknown,
): UseResourceResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const reqIdRef = useRef(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const depsKey = JSON.stringify(deps);
  const ready = fetcher !== null;

  const refetch = useCallback(
    (options?: RefetchOptions) => {
      const run = fetcherRef.current;
      // Prerequisites missing — stay in the loading state rather than
      // reporting a false empty result.
      if (!run) return;

      const quiet = options?.quiet === true;
      const reqId = ++reqIdRef.current;
      if (!quiet) {
        setLoading(true);
        setError(null);
      }
      run()
        .then((res) => {
          if (reqIdRef.current !== reqId) return;
          setData(res);
          setError(null);
        })
        .catch((e: unknown) => {
          if (reqIdRef.current !== reqId) return;
          // A failed background refresh keeps the last good data on screen,
          // but the error is still reported so the caller can say so.
          setError(e instanceof Error ? e : new Error(String(e)));
        })
        .finally(() => {
          if (reqIdRef.current !== reqId) return;
          setLoading(false);
        });
    },
    // `depsKey` is the serialized cache key, not a value read in the body —
    // the fetcher itself comes from a ref so it never has to be a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [depsKey],
  );

  useEffect(() => {
    refetch();
  }, [refetch, ready]);

  return { data, loading, error, refetch };
}
