"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { use, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { adminSetServiceMinOrderValue, fetchSellerHub } from "@/lib/adminActions";
import type { SellerHubSummary } from "@/types";

export default function SellerProfileTab({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const t = useTranslations("Admin.sellerHub");
  const tc = useTranslations("Admin.common");
  const { token } = useAuth();
  const [hub, setHub] = useState<SellerHubSummary | null>(null);
  const [minError, setMinError] = useState<string | null>(null);
  const minDebounceRef = useRef<Record<number, number>>({});

  useEffect(() => {
    if (!token) return;
    fetchSellerHub(Number(id), token).then(setHub).catch(() => {});
  }, [id, token]);

  if (!hub) return <div>{tc("loading")}</div>;

  const isApproved = hub.verification_status === "approved";

  const updateMin = (serviceId: number, raw: number) => {
    if (!token || !hub) return;
    const value = Number.isFinite(raw) ? Math.max(0, Math.min(100000, raw)) : 0;
    setHub({
      ...hub,
      services: hub.services.map((s) =>
        s.id === serviceId ? { ...s, min_order_value: value } : s,
      ),
    });
    if (minDebounceRef.current[serviceId]) {
      window.clearTimeout(minDebounceRef.current[serviceId]);
    }
    minDebounceRef.current[serviceId] = window.setTimeout(() => {
      adminSetServiceMinOrderValue(Number(id), serviceId, value, token)
        .then(() => setMinError(null))
        .catch((e) => {
          const detail = (e as { detail?: unknown })?.detail;
          setMinError(
            detail === "seller_not_active"
              ? t("profile.sellerNotActiveEdit")
              : t("profile.minSaveError"),
          );
        });
    }, 400);
  };

  const row: { label: string; value: React.ReactNode }[] = [
    { label: t("profile.businessName"), value: hub.business_name },
    { label: t("profile.ownerEmail"), value: hub.email },
    { label: t("profile.verificationStatus"), value: hub.verification_status },
    { label: t("profile.storeId"), value: hub.store_id ?? "—" },
    { label: t("profile.activeOrders"), value: hub.active_order_count },
    { label: t("profile.totalProducts"), value: hub.total_product_count },
  ];

  return (
    <div style={{ display: "grid", gap: "0.5rem", maxWidth: 600 }}>
      <h2 style={{ marginBottom: "0.5rem" }}>{t("tab.profile")}</h2>
      {row.map((r) => (
        <div
          key={r.label}
          style={{
            display: "grid",
            gridTemplateColumns: "180px 1fr",
            padding: "0.5rem 0",
            borderBottom: "1px solid var(--color-neutral-100)",
          }}
        >
          <span style={{ color: "var(--color-neutral-600)" }}>{r.label}</span>
          <span>{r.value}</span>
        </div>
      ))}

      {hub.services.length > 0 && (
        <section style={{ marginTop: "1.5rem" }}>
          <h3 style={{ marginBottom: "0.25rem" }}>{t("profile.minOrderValue")}</h3>
          <p style={{ color: "var(--color-neutral-600)", marginBottom: "0.75rem" }}>
            {t("profile.minOrderHint")}
          </p>
          {minError && (
            <p style={{ color: "var(--tomato-red-dark-1)" }}>{minError}</p>
          )}
          {hub.services.map((svc) => (
            <div
              key={svc.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                padding: "0.4rem 0",
              }}
            >
              <span style={{ minWidth: 160 }}>{svc.name}</span>
              <span>₹</span>
              <input
                type="number"
                min={0}
                max={100000}
                step={10}
                disabled={!isApproved}
                value={svc.min_order_value ?? 0}
                onChange={(e) => updateMin(svc.id, parseFloat(e.target.value))}
                aria-label={t("profile.minOrderAriaLabel", { name: svc.name })}
                style={{ width: 110, padding: "6px 8px", textAlign: "right" }}
              />
            </div>
          ))}
          {!isApproved && (
            <p style={{ color: "var(--color-neutral-600)", marginTop: "0.5rem" }}>
              {t("profile.minApprovedOnly")}
            </p>
          )}
        </section>
      )}
    </div>
  );
}
