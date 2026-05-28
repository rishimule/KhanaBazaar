"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { use, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { adminSetServiceMinOrderValue, fetchSellerHub } from "@/lib/adminActions";
import {
  GROUP_LABEL,
  adminListSellerCRs,
} from "@/lib/changeRequests";
import type {
  SellerHubSummary,
  SellerProfileChangeGroup,
  SellerProfileChangeRequest,
} from "@/types";

export default function SellerProfileTab({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const t = useTranslations("Admin.sellerHub");
  const tc = useTranslations("Admin.common");
  const ts = useTranslations("Admin.applications.status");
  const { token } = useAuth();
  const [hub, setHub] = useState<SellerHubSummary | null>(null);
  const [openCRs, setOpenCRs] = useState<SellerProfileChangeRequest[]>([]);
  const [minError, setMinError] = useState<string | null>(null);
  const minDebounceRef = useRef<Record<number, number>>({});

  useEffect(() => {
    if (!token) return;
    fetchSellerHub(Number(id), token).then(setHub).catch(() => {});
  }, [id, token]);

  // Open change requests by group — chips link straight to the admin detail
  // page. Errors are swallowed: the chips are nice-to-have, not required to
  // render the profile.
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    adminListSellerCRs(token, Number(id), "open")
      .then((rows) => {
        if (!cancelled) setOpenCRs(rows);
      })
      .catch(() => {
        if (!cancelled) setOpenCRs([]);
      });
    return () => {
      cancelled = true;
    };
  }, [id, token]);

  const openCRsByGroup = useMemo(() => {
    const map: Partial<
      Record<SellerProfileChangeGroup, SellerProfileChangeRequest>
    > = {};
    for (const cr of openCRs) {
      map[cr.group] = cr;
    }
    return map;
  }, [openCRs]);

  function renderChip(group: SellerProfileChangeGroup): React.ReactNode {
    const cr = openCRsByGroup[group];
    if (!cr) return null;
    return (
      <Link
        href={`/admin/sellers/${id}/requests/${cr.id}`}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 4,
          padding: "2px 10px",
          borderRadius: 999,
          background: "var(--saffron-yellow-light-1, #fffbeb)",
          color: "var(--saffron-yellow-dark-1, #92400e)",
          border: "1px solid var(--saffron-yellow-light-3, #fde68a)",
          fontSize: "0.78rem",
          fontWeight: 500,
          textDecoration: "none",
          whiteSpace: "nowrap",
        }}
      >
        <span aria-hidden>🔔</span>
        <span>Open change request</span>
      </Link>
    );
  }

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

  const row: {
    label: string;
    value: React.ReactNode;
    group?: SellerProfileChangeGroup;
  }[] = [
    {
      label: t("profile.businessName"),
      value: hub.business_name,
      group: "identity",
    },
    { label: t("profile.ownerEmail"), value: hub.email },
    { label: t("profile.verificationStatus"), value: ts(hub.verification_status) },
    {
      label: t("profile.storeId"),
      value: hub.store_id ?? "—",
      group: "store_basics",
    },
    { label: t("profile.activeOrders"), value: hub.active_order_count },
    { label: t("profile.totalProducts"), value: hub.total_product_count },
  ];

  // Strip of every open CR group on this seller — quick deep-links so the
  // admin can jump straight from the profile tab into the CR review screen.
  const openCRStrip = openCRs.length > 0 && (
    <section
      style={{
        marginTop: "0.5rem",
        marginBottom: "0.5rem",
        padding: "0.75rem 0.9rem",
        background: "var(--saffron-yellow-light-1, #fffbeb)",
        border: "1px solid var(--saffron-yellow-light-3, #fde68a)",
        borderRadius: "0.5rem",
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: "0.5rem",
      }}
    >
      <span
        style={{
          color: "var(--saffron-yellow-dark-1, #92400e)",
          fontWeight: 500,
        }}
      >
        Open change requests:
      </span>
      {openCRs.map((cr) => (
        <Link
          key={cr.id}
          href={`/admin/sellers/${id}/requests/${cr.id}`}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
            padding: "2px 10px",
            borderRadius: 999,
            background: "var(--white, #fff)",
            color: "var(--saffron-yellow-dark-1, #92400e)",
            border: "1px solid var(--saffron-yellow-light-3, #fde68a)",
            fontSize: "0.78rem",
            fontWeight: 500,
            textDecoration: "none",
          }}
        >
          <span aria-hidden>🔔</span>
          <span>{GROUP_LABEL[cr.group]}</span>
        </Link>
      ))}
    </section>
  );

  return (
    <div style={{ display: "grid", gap: "0.5rem", maxWidth: 600 }}>
      <h2 style={{ marginBottom: "0.5rem" }}>{t("tab.profile")}</h2>
      {openCRStrip}
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
          <span
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              flexWrap: "wrap",
            }}
          >
            <span>{r.value}</span>
            {r.group && renderChip(r.group)}
          </span>
        </div>
      ))}

      {hub.services.length > 0 && (
        <section style={{ marginTop: "1.5rem" }}>
          <h3
            style={{
              marginBottom: "0.25rem",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              flexWrap: "wrap",
            }}
          >
            <span>{t("profile.minOrderValue")}</span>
            {renderChip("services")}
          </h3>
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
