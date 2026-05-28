"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import DataTable, { Column } from "@/components/DataTable";
import Modal from "@/components/Modal";
import Pager from "@/components/Pager";
import { usePagedList } from "@/lib/usePagedList";
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import { useAuth } from "@/lib/AuthContext";
import { get, patch } from "@/lib/api";
import {
  SellerApplication,
  ApplicationCounts,
  PagedResponse,
  VerificationStatus,
  Service,
} from "@/types";
import ServicePicker from "@/components/ServicePicker";
import styles from "./page.module.css";
import mobileStyles from "@/components/DataTableCard.module.css";

const PAGE_SIZE = 20;

type Filter = VerificationStatus | "all";

type Translator = ReturnType<typeof useTranslations>;

function timeAgo(iso: string, t: Translator): string {
  const diff = Date.now() - new Date(iso).getTime();
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return t("timeAgo.seconds", { n: sec });
  const min = Math.floor(sec / 60);
  if (min < 60) return t("timeAgo.minutes", { n: min });
  const hr = Math.floor(min / 60);
  if (hr < 24) return t("timeAgo.hours", { n: hr });
  const day = Math.floor(hr / 24);
  return t("timeAgo.days", { n: day });
}

function statusPill(status: VerificationStatus, t: Translator) {
  const cls =
    status === "pending" ? styles.statusPending :
    status === "approved" ? styles.statusApproved :
    styles.statusRejected;
  const icon = status === "pending" ? "🟡" : status === "approved" ? "🟢" : "🔴";
  return (
    <span className={`${styles.statusPill} ${cls}`}>
      {icon} {t(`status.${status}`)}
    </span>
  );
}

export default function AdminSellersPage() {
  const t = useTranslations("Admin.applications");
  const tc = useTranslations("Admin.common");
  const router = useRouter();
  const { dbUser, token, loading: authLoading } = useAuth();

  const [filter, setFilter] = useState<Filter>("pending");
  const [counts, setCounts] = useState<ApplicationCounts>({
    pending: 0, approved: 0, rejected: 0, total: 0,
  });
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const debouncedQuery = useDebouncedValue(query, 300);
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

  const refreshCounts = useCallback(() => {
    if (!token) return;
    get<ApplicationCounts>("/api/v1/sellers/admin/applications/counts", token)
      .then(setCounts)
      .catch(() => {});
  }, [token]);

  const fetcher = useCallback(() => {
    if (!token) {
      return Promise.resolve<PagedResponse<SellerApplication>>({
        items: [], total: 0, page: 1, page_size: PAGE_SIZE,
      });
    }
    const sp = new URLSearchParams({
      status: filter,
      page: String(page),
      page_size: String(PAGE_SIZE),
    });
    if (debouncedQuery.trim()) sp.set("q", debouncedQuery.trim());
    return get<PagedResponse<SellerApplication>>(
      `/api/v1/sellers/admin/applications?${sp.toString()}`,
      token,
    );
  }, [token, filter, debouncedQuery, page]);

  const { data, loading: fetching, refetch } = usePagedList<
    PagedResponse<SellerApplication>
  >(fetcher, { token: Boolean(token), filter, debouncedQuery, page });
  const apps = data?.items ?? [];
  const total = data?.total ?? 0;

  async function handleApprove(sellerId: number) {
    if (!token) return;
    try {
      await patch(
        `/api/v1/sellers/admin/${sellerId}/verify`,
        { action: "approve" },
        token,
      );
      closeModal();
      refetch();
      refreshCounts();
    } catch {
      alert(t("genericError"));
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
      refetch();
      refreshCounts();
    } catch {
      alert(t("genericError"));
    }
  }

  async function saveServices() {
    if (!editingServices || !token) return;
    try {
      const { sellerId, ids } = editingServices;
      await patch(
        `/api/v1/sellers/admin/${sellerId}/services`,
        { service_ids: ids },
        token,
      );
      refetch();
      // Optimistically reflect the new service set in the open review modal.
      const chosen = allServices.filter((s) => ids.includes(s.id));
      setReviewing((prev) =>
        prev && prev.seller_id === sellerId ? { ...prev, services: chosen } : prev,
      );
      setEditingServices(null);
    } catch {
      /* silent */
    }
  }

  useEffect(() => {
    if (!authLoading && (!dbUser || dbUser.role !== "admin")) {
      router.push(dbUser ? "/" : "/login");
    }
  }, [authLoading, dbUser, router]);

  useEffect(() => {
    refreshCounts();
  }, [refreshCounts]);

  useEffect(() => {
    if (!token) return;
    get<Service[]>("/api/v1/catalog/services", token).then(setAllServices).catch(() => {});
  }, [token]);

  const columns: Column<SellerApplication>[] = [
    {
      key: "business_name",
      label: t("col.business"),
      render: (row) => <strong>{row.business_name}</strong>,
    },
    {
      key: "owner",
      label: t("col.owner"),
      render: (row) => (
        <div className={styles.ownerCell}>
          <span>{row.full_name}</span>
          <span className={styles.ownerEmail}>{row.email}</span>
        </div>
      ),
    },
    {
      key: "services",
      label: t("col.services"),
      render: (row) => {
        const visible = row.services.slice(0, 2);
        const extra = row.services.length - visible.length;
        return (
          <span>
            {visible.map((s) => (
              <span key={s.id} className={styles.categoryBadge}>{s.name}</span>
            ))}
            {extra > 0 && (
              <span className={styles.categoryBadge}>{t("moreServices", { n: extra })}</span>
            )}
          </span>
        );
      },
    },
    {
      key: "submitted_at",
      label: t("col.submitted"),
      render: (row) => timeAgo(row.submitted_at, t),
    },
    {
      key: "verification_status",
      label: t("col.status"),
      render: (row) => statusPill(row.verification_status, t),
    },
    {
      key: "actions",
      label: t("col.actions"),
      render: (row) => (
        <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
          <button
            className={styles.reviewBtn}
            onClick={() => setReviewing(row)}
          >
            {t("review")}
          </button>
          {row.verification_status === "approved" && (
            <Link
              href={`/admin/sellers/${row.seller_id}/products`}
              className={styles.reviewBtn}
              style={{ textDecoration: "none", display: "inline-flex", alignItems: "center" }}
            >
              {t("viewStore")}
            </Link>
          )}
        </div>
      ),
    },
  ];

  const emptyMsgMap: Record<Filter, string> = {
    pending: t("empty.pending"),
    approved: t("empty.approved"),
    rejected: t("empty.rejected"),
    all: t("empty.all"),
  };

  function tabClass(f: Filter) {
    return filter === f ? `${styles.tab} ${styles.tabActive}` : styles.tab;
  }
  function badgeClass(f: Filter) {
    return filter === f ? styles.tabBadge : `${styles.tabBadge} ${styles.tabBadgeInactive}`;
  }

  if (authLoading) {
    return (
      <div style={{ padding: "2rem", textAlign: "center", color: "var(--color-neutral-500)" }}>
        {tc("loading")}
      </div>
    );
  }

  return (
    <>
      <div className={styles.toolbar}>
        <div className={styles.tabs}>
          <button className={tabClass("pending")} onClick={() => { setFilter("pending"); setPage(1); }}>
            {t("tab.pending")} <span className={badgeClass("pending")}>{counts.pending}</span>
          </button>
          <button className={tabClass("approved")} onClick={() => { setFilter("approved"); setPage(1); }}>
            {t("tab.approved")} <span className={badgeClass("approved")}>{counts.approved}</span>
          </button>
          <button className={tabClass("rejected")} onClick={() => { setFilter("rejected"); setPage(1); }}>
            {t("tab.rejected")} <span className={badgeClass("rejected")}>{counts.rejected}</span>
          </button>
          <button className={tabClass("all")} onClick={() => { setFilter("all"); setPage(1); }}>
            {t("tab.all")} <span className={badgeClass("all")}>{counts.total}</span>
          </button>
        </div>
        <input
          type="search"
          className={styles.search}
          placeholder={t("searchPlaceholder")}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(1);
          }}
        />
      </div>

      {fetching && (
        <div style={{ padding: "1rem", color: "var(--color-neutral-500)" }}>
          {tc("loading")}
        </div>
      )}

      <DataTable
        columns={columns}
        data={apps}
        keyField="seller_id"
        emptyMessage={emptyMsgMap[filter]}
        mobileCardRender={(row) => (
          <>
            <div className={mobileStyles.cardTopRow}>
              <span className={mobileStyles.cardTitle}>{row.business_name}</span>
              {statusPill(row.verification_status, t)}
            </div>
            <div className={styles.ownerCell}>
              <span>{row.full_name}</span>
              <span className={styles.ownerEmail}>{row.email}</span>
            </div>
            <div className={mobileStyles.cardMeta}>
              {t("cardMeta", {
                n: row.services.length,
                ago: timeAgo(row.submitted_at, t),
              })}
            </div>
            <button
              className={styles.reviewBtn}
              style={{ width: "100%", minHeight: 44 }}
              onClick={() => setReviewing(row)}
            >
              {t("review")}
            </button>
          </>
        )}
      />
      <Pager
        page={page}
        pageSize={PAGE_SIZE}
        total={total}
        onPage={setPage}
        labels={{
          prev: t("prev"),
          next: t("next"),
          summary: (from, to, n) => t("showing", { from, to, total: n }),
        }}
      />

      {editingServices && (
        <Modal
          title={t("editServices")}
          onClose={() => setEditingServices(null)}
          footer={
            <>
              <button className="btn btn-outline" onClick={() => setEditingServices(null)}>{tc("cancel")}</button>
              <button
                className="btn btn-primary"
                disabled={editingServices.ids.length === 0}
                onClick={saveServices}
              >
                {tc("save")}
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
          title={t("reviewTitle", { name: reviewing.business_name })}
          onClose={() => closeModal()}
          footer={
            !rejectMode ? (
              <>
                <button className="btn btn-outline" onClick={() => closeModal()}>
                  {tc("cancel")}
                </button>
                {(reviewing.verification_status === "pending" ||
                  reviewing.verification_status === "rejected") && (
                  <button
                    className={styles.successBtn}
                    disabled={reviewing.services.length === 0}
                    title={reviewing.services.length === 0 ? t("setServicesFirst") : undefined}
                    onClick={() => handleApprove(reviewing.seller_id)}
                  >
                    {t("approve")}
                  </button>
                )}
                {(reviewing.verification_status === "pending" ||
                  reviewing.verification_status === "approved") && (
                  <button
                    className={styles.dangerBtn}
                    onClick={() => setRejectMode(true)}
                  >
                    {reviewing.verification_status === "approved" ? t("revoke") : t("reject")}
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
                  {tc("back")}
                </button>
                <button
                  className={styles.dangerBtn}
                  disabled={rejectReason.trim().length < 10}
                  onClick={() => handleReject(reviewing.seller_id)}
                >
                  {t("confirmReject")}
                </button>
              </>
            )
          }
        >
          {rejectMode ? (
            <>
              <div className={styles.detailsGroupTitle}>{t("rejectionReason")}</div>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                maxLength={500}
                rows={4}
                placeholder={t("rejectionPlaceholder")}
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
                {t("rejectionHint")}
              </div>
            </>
          ) : (
            <>
          {reviewing.verification_status === "rejected" && reviewing.rejection_reason && (
            <div className={styles.rejectionCallout}>
              <strong>{t("previousRejection")}</strong> {reviewing.rejection_reason}
            </div>
          )}
          <div className={styles.detailsGrid}>
            <div className={styles.detailsGroup}>
              <div className={styles.detailsGroupTitle}>{t("group.business")}</div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>{t("field.name")}</span>
                <span className={styles.detailsValue}>{reviewing.business_name}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>
                  {t("col.services")}
                  <button
                    type="button"
                    style={{ marginLeft: "0.5rem", border: "none", background: "transparent", cursor: "pointer" }}
                    onClick={() =>
                      setEditingServices({
                        sellerId: reviewing.seller_id,
                        ids: reviewing.services.map((s) => s.id),
                      })
                    }
                    aria-label={t("editServices")}
                  >
                    ✏️
                  </button>
                </span>
                <span className={styles.detailsValue}>
                  {reviewing.services.length === 0 ? (
                    <em>{t("none")}</em>
                  ) : (
                    reviewing.services.map((s) => (
                      <span key={s.id} className={styles.categoryBadge}>{s.name}</span>
                    ))
                  )}
                </span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>{t("field.addressLine1")}</span>
                <span className={styles.detailsValue}>{reviewing.address.address_line1}</span>
              </div>
              {reviewing.address.address_line2 && (
                <div className={styles.detailsRow}>
                  <span className={styles.detailsLabel}>{t("field.addressLine2")}</span>
                  <span className={styles.detailsValue}>{reviewing.address.address_line2}</span>
                </div>
              )}
              {reviewing.address.landmark && (
                <div className={styles.detailsRow}>
                  <span className={styles.detailsLabel}>{t("field.landmark")}</span>
                  <span className={styles.detailsValue}>{reviewing.address.landmark}</span>
                </div>
              )}
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>{t("field.city")}</span>
                <span className={styles.detailsValue}>{reviewing.address.city}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>{t("field.state")}</span>
                <span className={styles.detailsValue}>{reviewing.address.state}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>{t("field.pincode")}</span>
                <span className={styles.detailsValue}>{reviewing.address.pincode}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>{t("field.phone")}</span>
                <span className={styles.detailsValue}>{reviewing.phone}</span>
              </div>
            </div>
            <div className={styles.detailsGroup}>
              <div className={styles.detailsGroupTitle}>{t("group.compliance")}</div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>{t("field.gstNumber")}</span>
                <span className={styles.detailsValue}>{reviewing.gst_number || "—"}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>{t("field.fssaiLicense")}</span>
                <span className={styles.detailsValue}>{reviewing.fssai_license || "—"}</span>
              </div>
            </div>
            <div className={styles.detailsGroup}>
              <div className={styles.detailsGroupTitle}>{t("group.owner")}</div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>{t("field.fullName")}</span>
                <span className={styles.detailsValue}>{reviewing.full_name}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>{t("field.email")}</span>
                <span className={styles.detailsValue}>{reviewing.email}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>{t("field.submitted")}</span>
                <span className={styles.detailsValue}>
                  {new Date(reviewing.submitted_at).toLocaleString()}
                </span>
              </div>
            </div>
            <div className={styles.detailsGroup}>
              <div className={styles.detailsGroupTitle}>{t("group.banking")}</div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>{t("field.accountNumber")}</span>
                <span className={styles.detailsValue}>{reviewing.bank_account_number || "—"}</span>
              </div>
              <div className={styles.detailsRow}>
                <span className={styles.detailsLabel}>{t("field.ifsc")}</span>
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
