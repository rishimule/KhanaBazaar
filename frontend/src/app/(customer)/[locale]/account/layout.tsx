"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useTranslations } from "next-intl";
import DashboardLayout from "@/components/DashboardLayout";
import { useAuth } from "@/lib/AuthContext";
import type { UserRole } from "@/types";
import AccountSidebarFooter from "./_components/SidebarFooter";

function redirectForRole(role: UserRole): string {
  if (role === "admin") return "/admin";
  if (role === "seller") return "/seller";
  return "/";
}

export default function AccountLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { dbUser, loading } = useAuth();
  const t = useTranslations("Account");

  useEffect(() => {
    if (loading) return;
    if (!dbUser) {
      router.replace("/login");
      return;
    }
    if (dbUser.role !== "customer") {
      router.replace(redirectForRole(dbUser.role));
    }
  }, [loading, dbUser, router]);

  if (loading || !dbUser || dbUser.role !== "customer") {
    return (
      <div style={{ padding: "4rem", textAlign: "center", color: "var(--color-neutral-500)" }}>
        {t("loading")}
      </div>
    );
  }

  const customerNav = [
    { href: "/account", label: t("navDashboard"), icon: "🏠" },
    { href: "/account/orders", label: t("navOrders"), icon: "📦" },
    { href: "/account/favorites", label: t("navFavorites"), icon: "❤️" },
    { href: "/account/addresses", label: t("navAddresses"), icon: "📍" },
    { href: "/account/profile", label: t("navProfile"), icon: "👤" },
    { href: "/account/preferences", label: t("navPreferences"), icon: "⚙️" },
    { href: "/account/referrals", label: t("navReferrals"), icon: "🎁" },
    { href: "/account/support", label: t("navSupport"), icon: "💬" },
  ];

  const PAGE_TITLE_KEY: Record<string, string> = {
    "/account": "layoutTitle",
    "/account/orders": "layoutOrdersTitle",
    "/account/favorites": "layoutFavoritesTitle",
    "/account/addresses": "layoutAddressesTitle",
    "/account/profile": "layoutProfileTitle",
    "/account/preferences": "layoutPreferencesTitle",
    "/account/referrals": "layoutReferralsTitle",
    "/account/support": "layoutSupportTitle",
  };

  const title = t(PAGE_TITLE_KEY[pathname] ?? "layoutTitle");
  const roleName = dbUser.full_name || dbUser.email;

  return (
    <DashboardLayout
      role="customer"
      roleName={roleName}
      title={title}
      navItems={customerNav}
      footer={<AccountSidebarFooter />}
      avatarUrl={dbUser.avatar_url}
    >
      {children}
    </DashboardLayout>
  );
}
