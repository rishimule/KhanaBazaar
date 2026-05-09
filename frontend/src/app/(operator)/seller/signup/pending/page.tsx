"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import { VerificationStatus } from "@/types";
import styles from "./pending.module.css";

interface StatusResponse {
  verification_status: VerificationStatus;
  rejection_reason: string | null;
}

export default function SellerPendingPage() {
  const router = useRouter();
  const { token, dbUser, loading: authLoading, logout } = useAuth();

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

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  // Auth still hydrating
  if (authLoading || (token && status === null && !fetchError)) {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <div className={styles.spinner} />
          <p className={styles.body}>Loading&hellip;</p>
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
          <h1 className={styles.title}>Application not approved</h1>
          <p className={styles.body}>
            Your seller application was reviewed and could not be approved at
            this time.
          </p>
          {rejectionReason && (
            <div className={styles.rejectionCallout}>
              <p className={styles.rejectionTitle}>Reason for rejection</p>
              <p className={styles.rejectionReason}>{rejectionReason}</p>
            </div>
          )}
          <button
            type="button"
            className={styles.ctaBtn}
            onClick={() => router.push("/seller/signup?resubmit=true")}
          >
            Edit and resubmit
          </button>
          <div className={styles.logoutRow}>
            <button
              type="button"
              className={styles.logoutBtn}
              onClick={handleLogout}
            >
              Log out
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Pending (default)
  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <span className={styles.icon}>&#8987;</span>
        <h1 className={styles.title}>Application under review</h1>
        <p className={styles.body}>
          We&apos;ve received your application and our team is reviewing it.
        </p>
        {dbUser?.email && (
          <p className={styles.body}>
            We&apos;ll notify{" "}
            <span className={styles.email}>{dbUser.email}</span> once a
            decision is made.
          </p>
        )}
        <p className={styles.body}>Estimated time: 1&ndash;2 business days.</p>
        {fetchError && (
          <p className={`${styles.body} ${styles.fetchError}`}>
            Could not check status. Will retry automatically.
          </p>
        )}
        <div className={styles.logoutRow}>
          <button
            type="button"
            className={styles.logoutBtn}
            onClick={handleLogout}
          >
            Log out
          </button>
        </div>
      </div>
    </div>
  );
}
