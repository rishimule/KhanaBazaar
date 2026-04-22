"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import DataTable, { Column } from "@/components/DataTable";
import Modal from "@/components/Modal";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import { SellerApplication, ApplicationCounts, VerificationStatus } from "@/types";
import styles from "./page.module.css";

type Filter = VerificationStatus | "all";

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

function statusPill(status: VerificationStatus) {
  const cls =
    status === "pending" ? styles.statusPending :
    status === "approved" ? styles.statusApproved :
    styles.statusRejected;
  const icon = status === "pending" ? "🟡" : status === "approved" ? "🟢" : "🔴";
  return (
    <span className={`${styles.statusPill} ${cls}`}>
      {icon} {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

export default function AdminSellersPage() {
  const router = useRouter();
  const { dbUser, token, loading: authLoading } = useAuth();

  const [filter, setFilter] = useState<Filter>("pending");
  const [apps, setApps] = useState<SellerApplication[]>([]);
  const [counts, setCounts] = useState<ApplicationCounts>({
    pending: 0, approved: 0, rejected: 0, total: 0,
  });
  const [fetching, setFetching] = useState(true);
  const [reviewing, setReviewing] = useState<SellerApplication | null>(null);

  const fetchAll = useCallback(async () => {
    if (!token) return;
    setFetching(true);
    try {
      const [list, c] = await Promise.all([
        get<SellerApplication[]>(
          `/api/v1/sellers/admin/applications?status=${filter}`,
          token,
        ),
        get<ApplicationCounts>(
          "/api/v1/sellers/admin/applications/counts",
          token,
        ),
      ]);
      setApps(list);
      setCounts(c);
    } catch {
      /* toast handled by calling action in later tasks */
    } finally {
      setFetching(false);
    }
  }, [filter, token]);

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
      key: "business_category",
      label: "Category",
      render: (row) => (
        <span className={styles.categoryBadge}>{row.business_category}</span>
      ),
    },
    {
      key: "submitted_at",
      label: "Submitted",
      render: (row) => timeAgo(row.submitted_at),
    },
    {
      key: "verification_status",
      label: "Status",
      render: (row) => statusPill(row.verification_status),
    },
    {
      key: "actions",
      label: "Actions",
      render: (row) => (
        <button
          className={styles.reviewBtn}
          onClick={() => setReviewing(row)}
        >
          Review
        </button>
      ),
    },
  ];

  const emptyMsgMap: Record<Filter, string> = {
    pending: "No pending applications. 🎉",
    approved: "No approved sellers yet.",
    rejected: "No rejected applications.",
    all: "No seller applications yet.",
  };

  function tabClass(f: Filter) {
    return filter === f ? `${styles.tab} ${styles.tabActive}` : styles.tab;
  }
  function badgeClass(f: Filter) {
    return filter === f ? styles.tabBadge : `${styles.tabBadge} ${styles.tabBadgeInactive}`;
  }

  if (authLoading || fetching) {
    return (
      <div style={{ padding: "2rem", textAlign: "center", color: "var(--color-neutral-500)" }}>
        Loading…
      </div>
    );
  }

  return (
    <>
      <div className={styles.toolbar}>
        <div className={styles.tabs}>
          <button className={tabClass("pending")} onClick={() => setFilter("pending")}>
            Pending <span className={badgeClass("pending")}>{counts.pending}</span>
          </button>
          <button className={tabClass("approved")} onClick={() => setFilter("approved")}>
            Approved <span className={badgeClass("approved")}>{counts.approved}</span>
          </button>
          <button className={tabClass("rejected")} onClick={() => setFilter("rejected")}>
            Rejected <span className={badgeClass("rejected")}>{counts.rejected}</span>
          </button>
          <button className={tabClass("all")} onClick={() => setFilter("all")}>
            All <span className={badgeClass("all")}>{counts.total}</span>
          </button>
        </div>
        <span className={styles.total}>total: {counts.total}</span>
      </div>

      <DataTable
        columns={columns}
        data={apps}
        keyField="seller_id"
        emptyMessage={emptyMsgMap[filter]}
      />

      {reviewing && (
        <Modal
          title={`Review — ${reviewing.business_name}`}
          onClose={() => setReviewing(null)}
          footer={
            <button className="btn btn-outline" onClick={() => setReviewing(null)}>
              Close
            </button>
          }
        >
          {reviewing.verification_status === "rejected" && reviewing.rejection_reason && (
            <div className={styles.rejectionCallout}>
              <strong>Previous rejection:</strong> {reviewing.rejection_reason}
            </div>
          )}
          <div className={styles.detailsGrid}>
            <div className={styles.detailsGroup}>
              <div className={styles.detailsGroupTitle}>Business</div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>Name</span>
                <span className={styles.detailsValue}>{reviewing.business_name}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>Category</span>
                <span className={styles.detailsValue}>{reviewing.business_category}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>Address</span>
                <span className={styles.detailsValue}>{reviewing.address}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>Phone</span>
                <span className={styles.detailsValue}>{reviewing.phone}</span>
              </div>
            </div>
            <div className={styles.detailsGroup}>
              <div className={styles.detailsGroupTitle}>Compliance</div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>GST Number</span>
                <span className={styles.detailsValue}>{reviewing.gst_number}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>FSSAI License</span>
                <span className={styles.detailsValue}>{reviewing.fssai_license}</span>
              </div>
            </div>
            <div className={styles.detailsGroup}>
              <div className={styles.detailsGroupTitle}>Owner</div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>Full Name</span>
                <span className={styles.detailsValue}>{reviewing.full_name}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>Email</span>
                <span className={styles.detailsValue}>{reviewing.email}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>Submitted</span>
                <span className={styles.detailsValue}>
                  {new Date(reviewing.submitted_at).toLocaleString()}
                </span>
              </div>
            </div>
            <div className={styles.detailsGroup}>
              <div className={styles.detailsGroupTitle}>Banking</div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>Account Number</span>
                <span className={styles.detailsValue}>{reviewing.bank_account_number}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>IFSC</span>
                <span className={styles.detailsValue}>{reviewing.bank_ifsc}</span>
              </div>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
