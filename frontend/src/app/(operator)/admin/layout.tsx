"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import Navbar from "@/components/Navbar";
import { useAuth } from "@/lib/AuthContext";

const ADMIN_NAV = [
  { href: "/admin", label: "Dashboard", icon: "📊" },
  { href: "/admin/orders", label: "Orders", icon: "📦" },
  { href: "/admin/sellers", label: "Sellers", icon: "✅" },
  { href: "/admin/products", label: "Products", icon: "🛒" },
  { href: "/admin/categories", label: "Categories", icon: "🏷️" },
];

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { dbUser, loading } = useAuth();

  useEffect(() => {
    if (!loading && (!dbUser || dbUser.role !== "admin")) {
      router.replace(dbUser ? "/" : "/login");
    }
  }, [loading, dbUser, router]);

  if (loading || !dbUser || dbUser.role !== "admin") {
    return <div style={{ padding: "4rem", textAlign: "center", color: "var(--color-neutral-500)" }}>Loading…</div>;
  }

  const title =
    pathname === "/admin"
      ? "Admin Dashboard"
      : pathname === "/admin/sellers"
        ? "Seller Applications"
        : pathname === "/admin/products"
          ? "Product Catalog"
          : pathname === "/admin/categories"
            ? "Category Management"
            : pathname.startsWith("/admin/orders")
              ? "All Orders"
              : "Admin Panel";

  return (
    <>
      <Navbar variant="dashboard" />
      <DashboardLayout
        role="admin"
        roleName="Platform Admin"
        title={title}
        navItems={ADMIN_NAV}
      >
        {children}
      </DashboardLayout>
    </>
  );
}
