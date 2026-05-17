"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
//
// Approved-sellers list with drill-down to per-seller hub
// (Profile / Products / Orders / Activity).
//
// Application review (pending / approved / rejected) lives at
// /admin/sellers/applications.

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import DataTable, { Column } from "@/components/DataTable";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import { ApplicationCounts, SellerApplication } from "@/types";
import styles from "./page.module.css";
import mobileStyles from "@/components/DataTableCard.module.css";

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  return `${day}d ago`;
}

export default function AdminSellersListPage() {
  const router = useRouter();
  const { dbUser, token, loading: authLoading } = useAuth();

  const [sellers, setSellers] = useState<SellerApplication[]>([]);
  const [counts, setCounts] = useState<ApplicationCounts>({
    pending: 0,
    approved: 0,
    rejected: 0,
    total: 0,
  });
  const [fetching, setFetching] = useState(true);

  const fetchAll = useCallback(async () => {
    if (!token) return;
    setFetching(true);
    try {
      const [list, c] = await Promise.all([
        get<SellerApplication[]>(
          "/api/v1/sellers/admin/applications?status=approved",
          token,
        ),
        get<ApplicationCounts>(
          "/api/v1/sellers/admin/applications/counts",
          token,
        ),
      ]);
      setSellers(list);
      setCounts(c);
    } finally {
      setFetching(false);
    }
  }, [token]);

  useEffect(() => {
    if (!authLoading && (!dbUser || dbUser.role !== "admin")) {
      router.push(dbUser ? "/" : "/login");
      return;
    }
    if (!authLoading && dbUser && token) {
      fetchAll();
    }
  }, [authLoading, dbUser, token, router, fetchAll]);

  const columns: Column<SellerApplication>[] = [
    {
      key: "business_name",
      label: "Business",
      render: (row) => <strong>{row.business_name}</strong>,
    },
    {
      key: "owner",
      label: "Owner",
      render: (row) => (
        <div className={styles.ownerCell}>
          <span>{row.full_name}</span>
          <span className={styles.ownerEmail}>{row.email}</span>
        </div>
      ),
    },
    {
      key: "services",
      label: "Services",
      render: (row) => {
        const visible = row.services.slice(0, 2);
        const extra = row.services.length - visible.length;
        return (
          <span>
            {visible.map((s) => (
              <span key={s.id} className={styles.categoryBadge}>
                {s.name}
              </span>
            ))}
            {extra > 0 && (
              <span className={styles.categoryBadge}>+{extra} more</span>
            )}
          </span>
        );
      },
    },
    {
      key: "submitted_at",
      label: "Joined",
      render: (row) => timeAgo(row.submitted_at),
    },
    {
      key: "actions",
      label: "Actions",
      render: (row) => (
        <Link
          href={`/admin/sellers/${row.seller_id}/products`}
          className={styles.reviewBtn}
          style={{
            textDecoration: "none",
            display: "inline-flex",
            alignItems: "center",
          }}
        >
          View store
        </Link>
      ),
    },
  ];

  if (authLoading || fetching) {
    return (
      <div
        style={{
          padding: "2rem",
          textAlign: "center",
          color: "var(--color-neutral-500)",
        }}
      >
        Loading…
      </div>
    );
  }

  return (
    <>
      <div className={styles.toolbar}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
            flexWrap: "wrap",
          }}
        >
          <span style={{ color: "var(--color-neutral-600)" }}>
            {sellers.length} approved seller{sellers.length === 1 ? "" : "s"}
          </span>
          <Link
            href="/admin/sellers/applications"
            className="btn btn-primary"
            style={{ textDecoration: "none" }}
          >
            Manage applications
            {counts.pending > 0 && (
              <span
                style={{
                  marginLeft: 8,
                  background: "rgba(255,255,255,0.25)",
                  borderRadius: 999,
                  padding: "0.05rem 0.5rem",
                  fontSize: "0.85rem",
                }}
              >
                {counts.pending}
              </span>
            )}
          </Link>
        </div>
      </div>

      <DataTable
        columns={columns}
        data={sellers}
        keyField="seller_id"
        emptyMessage="No approved sellers yet. Approve one from the applications page."
        mobileCardRender={(row) => (
          <>
            <div className={mobileStyles.cardTopRow}>
              <span className={mobileStyles.cardTitle}>{row.business_name}</span>
            </div>
            <div className={styles.ownerCell}>
              <span>{row.full_name}</span>
              <span className={styles.ownerEmail}>{row.email}</span>
            </div>
            <div className={mobileStyles.cardMeta}>
              {row.services.length} service{row.services.length === 1 ? "" : "s"}{" "}
              · joined {timeAgo(row.submitted_at)}
            </div>
            <Link
              href={`/admin/sellers/${row.seller_id}/products`}
              className={styles.reviewBtn}
              style={{
                width: "100%",
                minHeight: 44,
                textDecoration: "none",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              View store
            </Link>
          </>
        )}
      />
    </>
  );
}
