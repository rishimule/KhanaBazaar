"use client";

import { usePathname } from "next/navigation";
import DashboardLayout from "@/components/DashboardLayout";

const SELLER_NAV = [
  { href: "/seller", label: "Dashboard", icon: "📊" },
  { href: "/seller/inventory", label: "Inventory", icon: "📦" },
];

export default function SellerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  // Derive title from current route
  const title =
    pathname === "/seller"
      ? "Seller Dashboard"
      : pathname === "/seller/inventory"
        ? "Inventory Management"
        : "Seller Portal";

  return (
    <DashboardLayout
      role="seller"
      roleName="Sharma General Store"
      title={title}
      navItems={SELLER_NAV}
    >
      {children}
    </DashboardLayout>
  );
}
