"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useTranslations } from "next-intl";
import DashboardLayout from "@/components/DashboardLayout";
import Navbar from "@/components/Navbar";
import { useAuth } from "@/lib/AuthContext";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const t = useTranslations("Admin");
  const pathname = usePathname();
  const router = useRouter();
  const { dbUser, loading } = useAuth();

  useEffect(() => {
    if (!loading && (!dbUser || dbUser.role !== "admin")) {
      router.replace(dbUser ? "/" : "/login");
    }
  }, [loading, dbUser, router]);

  if (loading || !dbUser || dbUser.role !== "admin") {
    return <div style={{ padding: "4rem", textAlign: "center", color: "var(--color-neutral-500)" }}>{t("common.loading")}</div>;
  }

  const adminNav = [
    { href: "/admin", label: t("nav.dashboard"), icon: "📊" },
    { href: "/admin/orders", label: t("nav.orders"), icon: "📦" },
    { href: "/admin/sellers", label: t("nav.sellers"), icon: "🏪" },
    { href: "/admin/customers", label: t("nav.customers"), icon: "👤" },
    { href: "/admin/sellers/applications", label: t("nav.applications"), icon: "✅" },
    { href: "/admin/change-requests", label: t("nav.changeRequests"), icon: "🔔" },
  { href: "/admin/notifications", label: t("nav.notifications"), icon: "📣" },
    { href: "/admin/onboarding-requests", label: t("nav.onboardingRequests"), icon: "📨" },
    { href: "/admin/referrals", label: t("nav.referrals"), icon: "🎁" },
    { href: "/admin/catalog", label: t("nav.catalog"), icon: "🗂️" },
    { href: "/admin/policies", label: t("nav.policies"), icon: "📜" },
    { href: "/admin/fees", label: t("nav.fees"), icon: "💳" },
    { href: "/admin/fees/queue", label: t("nav.feeQueue"), icon: "🧾" },
    // Operator-only tool; English label (fee content pages are English-only).
    { href: "/admin/fees/credit", label: "Wallet credit", icon: "👛" },
    { href: "/admin/settings", label: t("nav.settings"), icon: "⚙️" },
    { href: "/admin/devices", label: t("nav.devices"), icon: "🔐" },
  ];

  const title =
    pathname === "/admin"
      ? t("titles.dashboard")
      : pathname === "/admin/sellers"
        ? t("titles.sellers")
        : pathname.startsWith("/admin/sellers/applications")
          ? t("titles.applications")
          : pathname.startsWith("/admin/change-requests")
            ? t("titles.changeRequests")
            : pathname.startsWith("/admin/onboarding-requests")
            ? t("titles.onboardingRequests")
            : pathname.startsWith("/admin/referrals")
            ? t("titles.referrals")
            : pathname.startsWith("/admin/sellers/")
            ? t("titles.sellerStore")
            : pathname.startsWith("/admin/customers/")
            ? t("titles.customerDetail")
            : pathname === "/admin/customers"
            ? t("titles.customers")
            : pathname.startsWith("/admin/catalog")
              ? t("titles.catalog")
              : pathname.startsWith("/admin/orders")
                ? t("titles.orders")
                : pathname.startsWith("/admin/policies")
                  ? t("titles.policies")
                  : pathname.startsWith("/admin/fees/queue")
                    ? t("titles.feeQueue")
                    : pathname.startsWith("/admin/fees")
                      ? t("titles.fees")
                      : pathname.startsWith("/admin/settings")
                        ? t("titles.settings")
                        : pathname.startsWith("/admin/devices")
                          ? t("titles.devices")
                          : t("titles.panel");

  return (
    <>
      <Navbar variant="dashboard" />
      <DashboardLayout
        role="admin"
        roleName={t("common.adminName")}
        title={title}
        navItems={adminNav}
      >
        {children}
      </DashboardLayout>
    </>
  );
}
