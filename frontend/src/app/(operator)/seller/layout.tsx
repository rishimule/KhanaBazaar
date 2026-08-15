"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import DashboardLayout from "@/components/DashboardLayout";
import Navbar from "@/components/Navbar";
import SellerNotificationBell from "@/components/seller/SellerNotificationBell";
import SellerOrderAlerts from "@/components/seller/SellerOrderAlerts";
import LoadError from "@/components/LoadError";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import { Store, VerificationStatus } from "@/types";

export default function SellerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const t = useTranslations("Seller");
  const pathname = usePathname();
  const router = useRouter();
  const { dbUser, token, loading } = useAuth();
  const [storeName, setStoreName] = useState("");
  const [verificationStatus, setVerificationStatus] = useState<VerificationStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  // `null` used to mean both "still loading" and "the fetch failed", and the
  // guard below read the second as the first — trapping the seller on
  // "Loading…" forever. The error is now tracked separately so a transient
  // failure fails *open* (dashboard renders) with a visible warning.
  const [statusError, setStatusError] = useState<Error | null>(null);
  const [statusAttempt, setStatusAttempt] = useState(0);
  // null = unknown (never loaded / fetch failed) → the nav badge stays hidden.
  const [pendingOrders, setPendingOrders] = useState<number | null>(null);
  const onPendingCountChange = useCallback(
    (count: number | null) => setPendingOrders(count),
    []
  );

  // Compute before effects so value is stable
  const isSignupRoute = pathname.startsWith("/seller/signup");

  // Effect 1: role guard — only for non-signup routes
  useEffect(() => {
    if (isSignupRoute) return;
    if (!loading && (!dbUser || dbUser.role !== "seller")) {
      router.replace(dbUser ? "/" : "/login");
    }
  }, [loading, dbUser, router, isSignupRoute]);

  // Effect 2: store name fetch — only for non-signup routes
  useEffect(() => {
    if (isSignupRoute || loading || !dbUser || !token) return;
    get<Store[]>("/api/v1/stores/my", token)
      .then((stores) => {
        if (stores.length > 0) setStoreName(stores[0].name);
      })
      .catch(() => {
        // Deliberate, and the one place a swallow is defensible: the store name
        // is cosmetic chrome. The fallback is the neutral portal name, which
        // makes no claim about the business — unlike a "₹0" or an empty list.
        setStoreName("");
      });
  }, [loading, dbUser, token, isSignupRoute]);

  // Effect 3: verification status guard — only for non-signup routes
  useEffect(() => {
    if (isSignupRoute || loading || !dbUser || !token) return;
    get<{ verification_status: VerificationStatus; rejection_reason: string | null }>(
      "/api/v1/sellers/me/status",
      token
    )
      .then((data) => {
        setStatusError(null);
        setVerificationStatus(data.verification_status);
        if (data.verification_status !== "approved") {
          router.replace("/seller/signup/pending");
        }
      })
      .catch((e: unknown) => {
        // Fail open: an approved seller must not lose their dashboard to one
        // flaky GET. The banner below tells them the check didn't run.
        setStatusError(e instanceof Error ? e : new Error(String(e)));
      })
      .finally(() => setStatusLoading(false));
  }, [loading, dbUser, token, router, isSignupRoute, statusAttempt]);

  // --- All hooks above this line ---

  // Signup routes: render minimal Navbar wrapper, no DashboardLayout, no guard
  if (isSignupRoute) {
    return (
      <>
        <Navbar variant="signup" />
        {children}
      </>
    );
  }

  // Loading / auth guard
  if (loading || !dbUser || dbUser.role !== "seller") {
    return (
      <div style={{ padding: "4rem", textAlign: "center", color: "var(--color-neutral-500)" }}>
        {t("common.loading")}
      </div>
    );
  }

  // Waiting for verification status, or redirecting a non-approved seller.
  // A failed status check deliberately does NOT land here — see `statusError`.
  if (statusLoading || (!statusError && verificationStatus !== "approved")) {
    return (
      <div style={{ padding: "4rem", textAlign: "center", color: "var(--color-neutral-500)" }}>
        {t("common.loading")}
      </div>
    );
  }

  const sellerNav = [
    { href: "/seller", label: t("nav.dashboard"), icon: "📊" },
    { href: "/seller/profile", label: t("nav.profile"), icon: "🪪" },
    {
      href: "/seller/orders",
      label: t("nav.orders"),
      icon: "📦",
      badge: pendingOrders ?? undefined,
      badgeLabel: pendingOrders
        ? t("alerts.pendingBadgeLabel", { count: pendingOrders })
        : undefined,
    },
    { href: "/seller/inventory", label: t("nav.inventory"), icon: "🏷️" },
    { href: "/seller/settings", label: t("nav.settings"), icon: "⚙️" },
    { href: "/seller/plan", label: t("nav.plan"), icon: "💳" },
    { href: "/seller/credit", label: t("nav.credit"), icon: "🧾" },
    { href: "/seller/referrals", label: t("nav.referrals"), icon: "🎁" },
    { href: "/seller/store-qr", label: t("nav.storeQr"), icon: "🔳" },
    { href: "/seller/devices", label: t("nav.devices"), icon: "🔐" },
  ];

  // Derive title from current route
  const title =
    pathname === "/seller"
      ? t("titles.dashboard")
      : pathname === "/seller/inventory"
        ? t("titles.inventory")
        : pathname.startsWith("/seller/orders")
          ? t("titles.orders")
          : pathname.startsWith("/seller/settings")
            ? t("titles.settings")
            : pathname.startsWith("/seller/profile/requests")
              ? t("changeRequests.indexTitle")
              : pathname === "/seller/profile"
                ? t("titles.profile")
                : pathname.startsWith("/seller/plan")
                  ? t("titles.plan")
                  : pathname.startsWith("/seller/referrals")
                    ? t("titles.referrals")
                    : pathname.startsWith("/seller/credit")
                      ? t("titles.credit")
                      : pathname.startsWith("/seller/store-qr")
                        ? t("titles.storeQr")
                        : pathname.startsWith("/seller/devices")
                          ? t("titles.devices")
                          : t("titles.portal");

  return (
    <>
      <Navbar variant="dashboard" />
      <DashboardLayout
        role="seller"
        roleName={storeName || t("common.portalName")}
        title={title}
        navItems={sellerNav}
        avatarUrl={dbUser.avatar_url}
        headerAction={
          <>
            <SellerOrderAlerts onPendingCountChange={onPendingCountChange} />
            <SellerNotificationBell />
          </>
        }
      >
        {statusError && (
          <LoadError
            variant="banner"
            error={statusError}
            title={t("common.loadFailedTitle")}
            onRetry={() => {
              setStatusError(null);
              setStatusLoading(true);
              setStatusAttempt((n) => n + 1);
            }}
          />
        )}
        {children}
      </DashboardLayout>
    </>
  );
}
