"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import StoreQRCard from "@/components/StoreQRCard";
import cardStyles from "@/components/StoreQRCard.module.css";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import type { Store } from "@/types";

export default function SellerStoreQRPage() {
  const t = useTranslations("StoreQR");
  const { token, loading } = useAuth();
  const [store, setStore] = useState<Store | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (loading || !token) return;
    get<Store[]>("/api/v1/stores/my", token)
      .then((stores) => setStore(stores[0] ?? null))
      .catch(() => setStore(null))
      .finally(() => setLoaded(true));
  }, [loading, token]);

  if (!loaded) return null;

  if (!store) {
    return (
      <div className={cardStyles.empty}>
        <strong>{t("noStoreTitle")}</strong>
        <span>{t("noStoreBody")}</span>
      </div>
    );
  }

  return <StoreQRCard storeId={store.id} storeName={store.name} />;
}
