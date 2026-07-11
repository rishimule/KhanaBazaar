"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { use, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import StoreQRCard from "@/components/StoreQRCard";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import { fetchSellerHub } from "@/lib/adminActions";
import type { SellerHubSummary, Store } from "@/types";

export default function AdminQRTab({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const t = useTranslations("Admin.sellerHub");
  const tc = useTranslations("Admin.common");
  const { token } = useAuth();
  const [hub, setHub] = useState<SellerHubSummary | null>(null);
  const [store, setStore] = useState<Store | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!token) return;
    fetchSellerHub(Number(id), token)
      .then(async (h) => {
        setHub(h);
        if (h.store_id != null) {
          // public store-detail endpoint — no token required
          const s = await get<Store>(`/api/v1/stores/${h.store_id}`);
          setStore(s);
        }
      })
      .catch(() => setError(t("qr.loadError")))
      .finally(() => setLoaded(true));
  }, [id, token, t]);

  if (error) return <div>{error}</div>;
  if (!loaded) return <div>{tc("loading")}</div>;

  if (!hub?.store_id || !store) {
    return (
      <div
        style={{
          padding: "2rem",
          background: "var(--color-neutral-50)",
          borderRadius: 8,
          textAlign: "center",
          color: "var(--color-neutral-600)",
        }}
      >
        {t("qr.noStore")}
      </div>
    );
  }

  return <StoreQRCard storeId={store.id} storeName={store.name} />;
}
