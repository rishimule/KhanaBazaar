"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { useAuth } from "@/lib/AuthContext";
import type { UserRole } from "@/types";

const CUSTOMER_NAV = [
  { href: "/account/orders", label: "Orders", icon: "📦" },
  { href: "/account/settings", label: "Settings", icon: "⚙️" },
];

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
        Loading…
      </div>
    );
  }

  const title = pathname === "/account/settings" ? "Account settings" : "Account";
  const roleName = dbUser.full_name || dbUser.email;

  return (
    <DashboardLayout
      role="customer"
      roleName={roleName}
      title={title}
      navItems={CUSTOMER_NAV}
    >
      {children}
    </DashboardLayout>
  );
}
