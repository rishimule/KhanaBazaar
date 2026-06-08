"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import { VerificationStatus } from "@/types";
import LogoutConfirmDialog from "@/components/LogoutConfirmDialog";
import { useLogoutConfirm } from "@/lib/useLogoutConfirm";
import styles from "./pending.module.css";

interface StatusResponse {
  verification_status: VerificationStatus;
  rejection_reason: string | null;
}

export default function SellerPendingPage() {
  const t = useTranslations("Seller.pending");
  const tc = useTranslations("Seller.common");
  const router = useRouter();
  const { token, dbUser, loading: authLoading } = useAuth();
  const { open: logoutOpen, openDialog: openLogout, closeDialog: closeLogout } =
    useLogoutConfirm();

  const [status, setStatus] = useState<VerificationStatus | null>(null);
  const [rejectionReason, setRejectionReason] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (!token) {
      router.push("/login");
      return;
    }

    let cancelled = false;
    const intervalRef = { id: undefined as ReturnType<typeof setInterval> | undefined };

    const poll = async () => {
      try {
        const data = await get<StatusResponse>("/api/v1/sellers/me/status", token);
        if (cancelled) return;
        setStatus(data.verification_status);
        setRejectionReason(data.rejection_reason);
        setFetchError(false);
        if (data.verification_status === "approved") {
          clearInterval(intervalRef.id);
          router.push("/seller");
        }
      } catch {
        if (!cancelled) setFetchError(true);
      }
    };

    poll();
    intervalRef.id = setInterval(poll, 30000);

    return () => {
      cancelled = true;
      clearInterval(intervalRef.id);
    };
  }, [authLoading, token, router]);

  const logoutDialog = logoutOpen ? (
    <LogoutConfirmDialog onClose={closeLogout} onRedirect={() => router.push("/login")} />
  ) : null;

  // Auth still hydrating
  if (authLoading || (token && status === null && !fetchError)) {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <div className={styles.spinner} />
          <p className={styles.body}>{tc("loading")}</p>
        </div>
      </div>
    );
  }

  // Rejected
  if (status === "rejected") {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <span className={styles.icon}>&#10060;</span>
          <h1 className={styles.title}>{t("rejectedTitle")}</h1>
          <p className={styles.body}>{t("rejectedBody")}</p>
          {rejectionReason && (
            <div className={styles.rejectionCallout}>
              <p className={styles.rejectionTitle}>{t("rejectionReasonLabel")}</p>
              <p className={styles.rejectionReason}>{rejectionReason}</p>
            </div>
          )}
          <button
            type="button"
            className={styles.ctaBtn}
            onClick={() => router.push("/seller/signup?resubmit=true")}
          >
            {t("editAndResubmit")}
          </button>
          <div className={styles.logoutRow}>
            <button
              type="button"
              className={styles.logoutBtn}
              onClick={openLogout}
            >
              {t("logOut")}
            </button>
          </div>
        </div>
        {logoutDialog}
      </div>
    );
  }

  // Pending (default)
  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <span className={styles.icon}>&#8987;</span>
        <h1 className={styles.title}>{t("pendingTitle")}</h1>
        <p className={styles.body}>{t("pendingBody")}</p>
        {dbUser?.email && (
          <p className={styles.body}>
            {t.rich("notifyBody", {
              email: dbUser.email,
              em: (chunks) => <span className={styles.email}>{chunks}</span>,
            })}
          </p>
        )}
        <p className={styles.body}>{t("estimatedTime")}</p>
        {fetchError && (
          <p className={`${styles.body} ${styles.fetchError}`}>
            {t("fetchError")}
          </p>
        )}
        <div className={styles.logoutRow}>
          <button
            type="button"
            className={styles.logoutBtn}
            onClick={openLogout}
          >
            {t("logOut")}
          </button>
        </div>
      </div>
      {logoutDialog}
    </div>
  );
}
