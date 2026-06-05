// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
"use client";
import { useCallback, useEffect, useRef, useState } from "react";

import { authHeader, clearCreds, getCreds, setCreds } from "./devAuth";

const PAGE_SIZE = 20;
const POLL_MS = 5000;

export interface InboxResult<T> {
  basic: string | null;
  items: T[];
  total: number;
  page: number;
  q: string;
  loading: boolean;
  error: string | null;
  newCount: number;
  setQ: (v: string) => void;
  setPage: (p: number) => void;
  refresh: () => void;
  loadNew: () => void;
  login: () => void;
  logout: () => void;
  pageSize: number;
}

interface Row {
  id: number;
}

export function useInbox<T extends Row>(resource: "emails" | "sms"): InboxResult<T> {
  const [basic, setBasic] = useState<string | null>(null);
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newCount, setNewCount] = useState(0);
  const latestSeenId = useRef(0);

  useEffect(() => {
    setBasic(getCreds());
  }, []);

  const fetchPage = useCallback(async () => {
    if (!basic) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(page * PAGE_SIZE),
      });
      if (q) params.set("q", q);
      const resp = await fetch(`/api/v1/dev/${resource}?${params}`, {
        headers: authHeader(basic),
      });
      if (resp.status === 401) {
        clearCreds();
        setBasic(null);
        return;
      }
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setItems(data.items);
      setTotal(data.total);
      if (page === 0 && data.items.length > 0) {
        latestSeenId.current = data.items[0].id;
        setNewCount(0);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [basic, page, q, resource]);

  useEffect(() => {
    void fetchPage();
  }, [fetchPage]);

  // Poll for new messages only on page 1, when the tab is visible.
  useEffect(() => {
    if (!basic) return;
    const tick = async () => {
      if (document.hidden || page !== 0) return;
      const params = new URLSearchParams({ after: String(latestSeenId.current) });
      if (q) params.set("q", q);
      try {
        const resp = await fetch(`/api/v1/dev/${resource}/new-count?${params}`, {
          headers: authHeader(basic),
        });
        if (resp.ok) setNewCount((await resp.json()).count);
      } catch {
        /* ignore poll errors */
      }
    };
    const id = setInterval(tick, POLL_MS);
    return () => clearInterval(id);
  }, [basic, page, q, resource]);

  return {
    basic,
    items,
    total,
    page,
    q,
    loading,
    error,
    newCount,
    setQ: (v) => {
      setPage(0);
      setQ(v);
    },
    setPage,
    refresh: fetchPage,
    loadNew: () => {
      setPage(0);
      void fetchPage();
    },
    // Called after a successful login: pull the freshly-stored creds into
    // state so the page re-renders out of the login gate and fetchPage (which
    // is gated on `basic`) runs.
    login: () => setBasic(getCreds()),
    logout: () => {
      clearCreds();
      setBasic(null);
    },
    pageSize: PAGE_SIZE,
  };
}

export function useLogin(onAuthed: () => void) {
  const [err, setErr] = useState<string | null>(null);
  const attempt = useCallback(
    async (user: string, pass: string) => {
      const basic = btoa(`${user}:${pass}`);
      const resp = await fetch(`/api/v1/dev/emails/new-count?after=0`, {
        headers: authHeader(basic),
      });
      if (resp.ok) {
        setCreds(user, pass);
        onAuthed();
        return;
      }
      setErr(resp.status === 401 ? "Invalid credentials" : `Error ${resp.status}`);
    },
    [onAuthed],
  );
  return { attempt, err };
}
