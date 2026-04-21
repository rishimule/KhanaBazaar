"use client";

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

  const fetchStatus = async (tok: string) => {
    try {
      const data = await get<StatusResponse>("/api/v1/sellers/me/status", tok);
      setStatus(data.verification_status);
      setRejectionReason(data.rejection_reason);
      setFetchError(false);
      return data.verification_status;
    } catch {
      setFetchError(true);
      return null;
    }
  };

  useEffect(() => {
    if (authLoading) return;
    if (!token) {
      router.push("/login");
      return;
    }

    let cancelled = false;

    // Initial fetch
    async function runInitialFetch() {
      const s = await fetchStatus(token as string);
      if (!cancelled && s === "approved") router.push("/seller");
    }
    runInitialFetch();

    // Poll every 30 seconds
    const interval = setInterval(async () => {
      const s = await fetchStatus(token as string);
      if (!cancelled && s === "approved") {
        clearInterval(interval);
        router.push("/seller");
      }
    }, 30000);

    return () => {
      cancelled = true;
      clearInterval(interval);
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
          <a
            href="/seller/signup?resubmit=true"
            className={styles.ctaBtn}
          >
            Edit and resubmit
          </a>
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
          <p className={styles.body} style={{ color: "var(--color-error)", marginTop: "var(--space-4)" }}>
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
