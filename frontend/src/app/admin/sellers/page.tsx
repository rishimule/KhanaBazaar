"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import DataTable, { Column } from "@/components/DataTable";
import Modal from "@/components/Modal";
import { useAuth } from "@/lib/AuthContext";
import { get, patch } from "@/lib/api";
import { SellerApplication, ApplicationCounts, VerificationStatus, Service } from "@/types";
import ServicePicker from "@/components/ServicePicker";
import styles from "./page.module.css";
import mobileStyles from "@/components/DataTableCard.module.css";

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
  const [rejectMode, setRejectMode] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [editingServices, setEditingServices] = useState<{ sellerId: number; ids: number[] } | null>(null);
  const [allServices, setAllServices] = useState<Service[]>([]);

  function closeModal() {
    setReviewing(null);
    setRejectMode(false);
    setRejectReason("");
  }

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

  async function handleApprove(sellerId: number) {
    if (!token) return;
    try {
      await patch(
        `/api/v1/sellers/admin/${sellerId}/verify`,
        { action: "approve" },
        token,
      );
      closeModal();
      await fetchAll();
    } catch {
      alert("Something went wrong, please try again");
    }
  }

  async function handleReject(sellerId: number) {
    if (!token || rejectReason.trim().length < 10) return;
    try {
      await patch(
        `/api/v1/sellers/admin/${sellerId}/verify`,
        { action: "reject", rejection_reason: rejectReason.trim() },
        token,
      );
      closeModal();
      await fetchAll();
    } catch {
      alert("Something went wrong, please try again");
    }
  }

  async function saveServices() {
    if (!editingServices || !token) return;
    try {
      await patch(
        `/api/v1/sellers/admin/${editingServices.sellerId}/services`,
        { service_ids: editingServices.ids },
        token,
      );
      const fresh = await get<SellerApplication[]>(
        `/api/v1/sellers/admin/applications?status=${filter}`,
        token,
      );
      setApps(fresh);
      setReviewing((prev) =>
        prev && prev.seller_id === editingServices.sellerId
          ? {
              ...prev,
              services:
                fresh.find((r) => r.seller_id === prev.seller_id)?.services ?? prev.services,
            }
          : prev,
      );
      setEditingServices(null);
    } catch {
      /* silent */
    }
  }

  useEffect(() => {
    if (!authLoading && (!dbUser || dbUser.role !== "admin")) {
      router.push(dbUser ? "/" : "/login");
      return;
    }
    if (!authLoading && dbUser && token) {
      fetchAll();
    }
  }, [authLoading, dbUser, token, router, fetchAll]);

  useEffect(() => {
    if (!token) return;
    get<Service[]>("/api/v1/catalog/services", token).then(setAllServices).catch(() => {});
  }, [token]);

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
              <span key={s.id} className={styles.categoryBadge}>{s.name}</span>
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
      </div>

      <DataTable
        columns={columns}
        data={apps}
        keyField="seller_id"
        emptyMessage={emptyMsgMap[filter]}
        mobileCardRender={(row) => (
          <>
            <div className={mobileStyles.cardTopRow}>
              <span className={mobileStyles.cardTitle}>{row.business_name}</span>
              {statusPill(row.verification_status)}
            </div>
            <div className={styles.ownerCell}>
              <span>{row.full_name}</span>
              <span className={styles.ownerEmail}>{row.email}</span>
            </div>
            <div className={mobileStyles.cardMeta}>
              {row.services.length} service{row.services.length === 1 ? "" : "s"} • {timeAgo(row.submitted_at)}
            </div>
            <button
              className={styles.reviewBtn}
              style={{ width: "100%", minHeight: 44 }}
              onClick={() => setReviewing(row)}
            >
              Review
            </button>
          </>
        )}
      />

      {editingServices && (
        <Modal
          title="Edit services"
          onClose={() => setEditingServices(null)}
          footer={
            <>
              <button className="btn btn-outline" onClick={() => setEditingServices(null)}>Cancel</button>
              <button
                className="btn btn-primary"
                disabled={editingServices.ids.length === 0}
                onClick={saveServices}
              >
                Save
              </button>
            </>
          }
        >
          <ServicePicker
            selectedIds={editingServices.ids}
            onChange={(ids) => setEditingServices({ ...editingServices, ids })}
            token={token}
            services={allServices.length > 0 ? allServices : undefined}
          />
        </Modal>
      )}

      {reviewing && (
        <Modal
          title={`Review — ${reviewing.business_name}`}
          onClose={() => closeModal()}
          footer={
            !rejectMode ? (
              <>
                <button className="btn btn-outline" onClick={() => closeModal()}>
                  Cancel
                </button>
                {(reviewing.verification_status === "pending" ||
                  reviewing.verification_status === "rejected") && (
                  <button
                    className={styles.successBtn}
                    disabled={reviewing.services.length === 0}
                    title={reviewing.services.length === 0 ? "Set services before approving" : undefined}
                    onClick={() => handleApprove(reviewing.seller_id)}
                  >
                    Approve
                  </button>
                )}
                {(reviewing.verification_status === "pending" ||
                  reviewing.verification_status === "approved") && (
                  <button
                    className={styles.dangerBtn}
                    onClick={() => setRejectMode(true)}
                  >
                    {reviewing.verification_status === "approved" ? "Revoke" : "Reject"}
                  </button>
                )}
              </>
            ) : (
              <>
                <button
                  className="btn btn-outline"
                  onClick={() => {
                    setRejectMode(false);
                    setRejectReason("");
                  }}
                >
                  Back
                </button>
                <button
                  className={styles.dangerBtn}
                  disabled={rejectReason.trim().length < 10}
                  onClick={() => handleReject(reviewing.seller_id)}
                >
                  Confirm Reject
                </button>
              </>
            )
          }
        >
          {rejectMode ? (
            <>
              <div className={styles.detailsGroupTitle}>Rejection Reason</div>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                maxLength={500}
                rows={4}
                placeholder="Explain what the seller needs to fix…"
                style={{
                  width: "100%",
                  padding: "0.6rem",
                  border: "1px solid var(--color-neutral-300)",
                  borderRadius: "6px",
                  fontFamily: "inherit",
                  fontSize: "0.95rem",
                  resize: "vertical",
                }}
              />
              <div className={styles.rejectionHint}>
                Common reasons: Invalid GST, Invalid FSSAI, Address mismatch, Bank details unclear.
                Minimum 10 characters.
              </div>
            </>
          ) : (
            <>
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
                <span className={styles.detailsLabel}>
                  Services
                  <button
                    type="button"
                    style={{ marginLeft: "0.5rem", border: "none", background: "transparent", cursor: "pointer" }}
                    onClick={() =>
                      setEditingServices({
                        sellerId: reviewing.seller_id,
                        ids: reviewing.services.map((s) => s.id),
                      })
                    }
                    aria-label="Edit services"
                  >
                    ✏️
                  </button>
                </span>
                <span className={styles.detailsValue}>
                  {reviewing.services.length === 0 ? (
                    <em>None</em>
                  ) : (
                    reviewing.services.map((s) => (
                      <span key={s.id} className={styles.categoryBadge}>{s.name}</span>
                    ))
                  )}
                </span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>Address line 1</span>
                <span className={styles.detailsValue}>{reviewing.address.address_line1}</span>
              </div>
              {reviewing.address.address_line2 && (
                <div className={styles.detailsRow}>
                  <span className={styles.detailsLabel}>Address line 2</span>
                  <span className={styles.detailsValue}>{reviewing.address.address_line2}</span>
                </div>
              )}
              {reviewing.address.landmark && (
                <div className={styles.detailsRow}>
                  <span className={styles.detailsLabel}>Landmark</span>
                  <span className={styles.detailsValue}>{reviewing.address.landmark}</span>
                </div>
              )}
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>City</span>
                <span className={styles.detailsValue}>{reviewing.address.city}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>State</span>
                <span className={styles.detailsValue}>{reviewing.address.state}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>Pincode</span>
                <span className={styles.detailsValue}>{reviewing.address.pincode}</span>
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
                <span className={styles.detailsValue}>{reviewing.gst_number || "—"}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>FSSAI License</span>
                <span className={styles.detailsValue}>{reviewing.fssai_license || "—"}</span>
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
                <span className={styles.detailsValue}>{reviewing.bank_account_number || "—"}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>IFSC</span>
                <span className={styles.detailsValue}>{reviewing.bank_ifsc || "—"}</span>
              </div>
            </div>
          </div>
            </>
          )}
        </Modal>
      )}
    </>
  );
}
