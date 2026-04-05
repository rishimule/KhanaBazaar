"use client";

import { usePathname } from "next/navigation";
import DashboardLayout from "@/components/DashboardLayout";

const ADMIN_NAV = [
  { href: "/admin", label: "Dashboard", icon: "📊" },
  { href: "/admin/products", label: "Products", icon: "📦" },
  { href: "/admin/categories", label: "Categories", icon: "🏷️" },
];

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  const title =
    pathname === "/admin"
      ? "Admin Dashboard"
      : pathname === "/admin/products"
        ? "Product Catalog"
        : pathname === "/admin/categories"
          ? "Category Management"
          : "Admin Panel";

  return (
    <DashboardLayout
      role="admin"
      roleName="Platform Admin"
      title={title}
      navItems={ADMIN_NAV}
    >
      {children}
    </DashboardLayout>
  );
}
