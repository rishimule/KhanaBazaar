"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { use, useEffect, useState } from "react";
import { useAuth } from "@/lib/AuthContext";
import { fetchSellerHub } from "@/lib/adminActions";
import type { SellerHubSummary } from "@/types";

export default function SellerProfileTab({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { token } = useAuth();
  const [hub, setHub] = useState<SellerHubSummary | null>(null);
  useEffect(() => {
    if (!token) return;
    fetchSellerHub(Number(id), token).then(setHub).catch(() => {});
  }, [id, token]);

  if (!hub) return <div>Loading…</div>;

  const row: { label: string; value: React.ReactNode }[] = [
    { label: "Business name", value: hub.business_name },
    { label: "Owner email", value: hub.email },
    { label: "Verification status", value: hub.verification_status },
    { label: "Store id", value: hub.store_id ?? "—" },
    { label: "Active orders", value: hub.active_order_count },
    { label: "Total products", value: hub.total_product_count },
  ];

  return (
    <div style={{ display: "grid", gap: "0.5rem", maxWidth: 600 }}>
      <h2 style={{ marginBottom: "0.5rem" }}>Profile</h2>
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
    </div>
  );
}
