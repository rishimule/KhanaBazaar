"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import { Store } from "@/types";

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
  const router = useRouter();
  const { dbUser, token, loading } = useAuth();
  const [storeName, setStoreName] = useState("Seller Portal");

  useEffect(() => {
    if (!loading && (!dbUser || dbUser.role !== "seller")) {
      router.push(dbUser ? "/" : "/login");
      return;
    }
    if (!loading && dbUser && token) {
      get<Store[]>("/api/v1/stores/my", token)
        .then((stores) => {
          if (stores.length > 0) setStoreName(stores[0].name);
        })
        .catch(() => {});
    }
  }, [loading, dbUser, token, router]);

  if (loading || !dbUser || dbUser.role !== "seller") {
    return <div style={{ padding: "4rem", textAlign: "center", color: "var(--color-neutral-500)" }}>Loading…</div>;
  }

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
      roleName={storeName}
      title={title}
      navItems={SELLER_NAV}
    >
      {children}
    </DashboardLayout>
  );
}
