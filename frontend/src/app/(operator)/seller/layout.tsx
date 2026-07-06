"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import DashboardLayout from "@/components/DashboardLayout";
import Navbar from "@/components/Navbar";
import SellerNotificationBell from "@/components/seller/SellerNotificationBell";
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
      .catch(() => {});
  }, [loading, dbUser, token, isSignupRoute]);

  // Effect 3: verification status guard — only for non-signup routes
  useEffect(() => {
    if (isSignupRoute || loading || !dbUser || !token) return;
    get<{ verification_status: VerificationStatus; rejection_reason: string | null }>(
      "/api/v1/sellers/me/status",
      token
    )
      .then((data) => {
        setVerificationStatus(data.verification_status);
        if (data.verification_status !== "approved") {
          router.replace("/seller/signup/pending");
        }
      })
      .catch(() => {
        // On error, don't block the UI — allow dashboard to load
      })
      .finally(() => setStatusLoading(false));
  }, [loading, dbUser, token, router, isSignupRoute]);

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

  // Waiting for verification status or redirecting
  if (statusLoading || verificationStatus === null || verificationStatus !== "approved") {
    return (
      <div style={{ padding: "4rem", textAlign: "center", color: "var(--color-neutral-500)" }}>
        {t("common.loading")}
      </div>
    );
  }

  const sellerNav = [
    { href: "/seller", label: t("nav.dashboard"), icon: "📊" },
    { href: "/seller/profile", label: t("nav.profile"), icon: "🪪" },
    { href: "/seller/orders", label: t("nav.orders"), icon: "📦" },
    { href: "/seller/inventory", label: t("nav.inventory"), icon: "🏷️" },
    { href: "/seller/settings", label: t("nav.settings"), icon: "⚙️" },
    { href: "/seller/plan", label: t("nav.plan"), icon: "💳" },
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
        headerAction={<SellerNotificationBell />}
      >
        {children}
      </DashboardLayout>
    </>
  );
}
