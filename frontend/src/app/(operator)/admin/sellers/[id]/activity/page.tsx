"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { use, useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import ActivityTable from "@/components/admin/ActivityTable";
import { useAuth } from "@/lib/AuthContext";
import { fetchSellerActivity } from "@/lib/adminActions";
import type { AdminActionLog } from "@/types";

export default function AdminActivityTab({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const t = useTranslations("Admin.sellerHub");
  const { token } = useAuth();
  const [rows, setRows] = useState<AdminActionLog[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const loadInitial = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const page = await fetchSellerActivity(Number(id), token);
      setRows(page.items);
      setCursor(page.next_cursor);
    } finally {
      setLoading(false);
    }
  }, [id, token]);

  useEffect(() => {
    loadInitial();
  }, [loadInitial]);

  async function loadMore() {
    if (!token || !cursor) return;
    setLoading(true);
    try {
      const page = await fetchSellerActivity(Number(id), token, cursor);
      setRows((prev) => [...prev, ...page.items]);
      setCursor(page.next_cursor);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h2 style={{ marginBottom: "0.75rem" }}>{t("activity.heading")}</h2>
      <ActivityTable
        rows={rows}
        hasMore={cursor !== null}
        loading={loading}
        onLoadMore={loadMore}
      />
    </div>
  );
}
