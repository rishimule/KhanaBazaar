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
    { href: "/admin/sellers/applications", label: t("nav.applications"), icon: "✅" },
    { href: "/admin/catalog", label: t("nav.catalog"), icon: "🗂️" },
  ];

  const title =
    pathname === "/admin"
      ? t("titles.dashboard")
      : pathname === "/admin/sellers"
        ? t("titles.sellers")
        : pathname.startsWith("/admin/sellers/applications")
          ? t("titles.applications")
          : pathname.startsWith("/admin/sellers/")
            ? t("titles.sellerStore")
            : pathname.startsWith("/admin/catalog")
              ? t("titles.catalog")
              : pathname.startsWith("/admin/orders")
                ? t("titles.orders")
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
