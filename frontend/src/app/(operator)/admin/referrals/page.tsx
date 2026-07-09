"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import DataTable, { Column } from "@/components/DataTable";
import Modal from "@/components/Modal";
import { useAuth } from "@/lib/AuthContext";
import {
  adminApproveReferral,
  adminListReferrals,
  adminRejectReferral,
  getReferralSettings,
  patchReferralSettings,
  type Referral,
  type ReferralStatus,
  type ReferralTargetRole,
} from "@/lib/referrals";
import styles from "./page.module.css";

const STATUSES: ReferralStatus[] = [
  "pending_review",
  "approved",
  "active",
  "rejected",
  "expired",
];
const ROLES: ReferralTargetRole[] = ["customer", "seller"];

export default function AdminReferralsPage() {
  const t = useTranslations("Referrals");
  const { token } = useAuth();

  const [status, setStatus] = useState<string>("pending_review");
  const [role, setRole] = useState<string>("all");
  const [rows, setRows] = useState<Referral[]>([]);
  const [loading, setLoading] = useState(true);
  const [requireApproval, setRequireApproval] = useState<boolean | null>(null);
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const [rejectTarget, setRejectTarget] = useState<Referral | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const refetch = useCallback(() => {
    if (!token) return;
    setLoading(true);
    adminListReferrals(token, {
      status: status === "all" ? undefined : (status as ReferralStatus),
      targetRole: role === "all" ? undefined : (role as ReferralTargetRole),
      pageSize: 100,
    })
      .then((res) => setRows(res.items))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [token, status, role]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  useEffect(() => {
    if (!token) return;
    getReferralSettings(token)
      .then((s) => setRequireApproval(s.require_admin_approval))
      .catch(() => setRequireApproval(null));
  }, [token]);

  const toggleApproval = async () => {
    if (!token || requireApproval === null) return;
    const next = !requireApproval;
    setRequireApproval(next);
    try {
      const saved = await patchReferralSettings(token, next);
      setRequireApproval(saved.require_admin_approval);
    } catch {
      setRequireApproval(!next); // revert on failure
    }
  };

  const approve = async (id: number) => {
    if (!token) return;
    setUpdatingId(id);
    try {
      await adminApproveReferral(token, id);
      refetch();
    } finally {
      setUpdatingId(null);
    }
  };

  const confirmReject = async () => {
    if (!token || !rejectTarget || !rejectReason.trim()) return;
    setUpdatingId(rejectTarget.id);
    try {
      await adminRejectReferral(token, rejectTarget.id, rejectReason.trim());
      setRejectTarget(null);
      setRejectReason("");
      refetch();
    } finally {
      setUpdatingId(null);
    }
  };

  const columns: Column<Referral>[] = [
    { key: "invitee_name", label: t("admin.colInvitee") },
    {
      key: "contact",
      label: t("admin.colContact"),
      render: (r) => (
        <span className={styles.muted}>{r.invitee_email || r.invitee_phone || "—"}</span>
      ),
    },
    { key: "target_role", label: t("admin.colRole"), render: (r) => t(`role.${r.target_role}`) },
    {
      key: "source",
      label: t("admin.colSource"),
      render: (r) => (
        <span className={styles.muted}>{`${t(`role.${r.source_role}`)} #${r.source_user_id}`}</span>
      ),
    },
    {
      key: "location",
      label: t("admin.colLocation"),
      render: (r) => (
        <span className={styles.muted}>{`${r.location_area}, ${r.location_state}`}</span>
      ),
    },
    {
      key: "status",
      label: t("admin.colStatus"),
      render: (r) => <span className={styles.statusBadge}>{t(`status.${r.status}`)}</span>,
    },
    {
      key: "created_at",
      label: t("admin.colCreated"),
      render: (r) =>
        new Date(r.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short" }),
    },
    {
      key: "actions",
      label: t("admin.colActions"),
      render: (r) =>
        r.status === "pending_review" ? (
          <div className={styles.actions}>
            <button
              type="button"
              className="btn btn-primary"
              disabled={updatingId === r.id}
              onClick={() => approve(r.id)}
            >
              {t("admin.approve")}
            </button>
            <button
              type="button"
              className={styles.rejectBtn}
              disabled={updatingId === r.id}
              onClick={() => {
                setRejectTarget(r);
                setRejectReason("");
              }}
            >
              {t("admin.reject")}
            </button>
          </div>
        ) : (
          <span className={styles.muted}>—</span>
        ),
    },
  ];

  return (
    <div className={styles.page}>
      {requireApproval !== null && (
        <div className={styles.settingsCard}>
          <div>
            <div className={styles.settingsLabel}>{t("admin.requireApprovalLabel")}</div>
            <div className={styles.settingsHelp}>{t("admin.requireApprovalHelp")}</div>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={requireApproval}
            aria-label={t("admin.requireApprovalLabel")}
            className={requireApproval ? styles.toggleOn : styles.toggleOff}
            onClick={toggleApproval}
          >
            <span className={styles.toggleKnob} />
          </button>
        </div>
      )}

      <div className={styles.toolbar}>
        <div className={styles.filters}>
          <select
            className={styles.select}
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            aria-label={t("admin.filterStatus")}
          >
            <option value="all">{t("admin.filterAll")}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{t(`status.${s}`)}</option>
            ))}
          </select>
          <select
            className={styles.select}
            value={role}
            onChange={(e) => setRole(e.target.value)}
            aria-label={t("admin.filterRole")}
          >
            <option value="all">{t("admin.filterAll")}</option>
            {ROLES.map((r) => (
              <option key={r} value={r}>{t(`role.${r}`)}</option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <p className={styles.muted}>{t("loading")}</p>
      ) : (
        <DataTable
          columns={columns}
          data={rows}
          keyField="id"
          emptyMessage={t("admin.empty")}
        />
      )}

      {rejectTarget && (
        <Modal
          title={t("admin.rejectTitle")}
          onClose={() => setRejectTarget(null)}
          footer={
            <>
              <button type="button" className="btn btn-secondary" onClick={() => setRejectTarget(null)}>
                {t("admin.cancel")}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!rejectReason.trim() || updatingId === rejectTarget.id}
                onClick={confirmReject}
              >
                {t("admin.rejectConfirm")}
              </button>
            </>
          }
        >
          <label className={styles.settingsLabel} htmlFor="reject-reason">
            {t("admin.rejectReasonLabel")}
          </label>
          <textarea
            id="reject-reason"
            className={styles.reasonInput}
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            maxLength={300}
            rows={3}
          />
        </Modal>
      )}
    </div>
  );
}
