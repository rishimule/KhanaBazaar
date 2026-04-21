"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { useAuth } from "@/lib/AuthContext";
import { get } from "@/lib/api";
import { Store, VerificationStatus } from "@/types";

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
  const [verificationStatus, setVerificationStatus] = useState<VerificationStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);

  // Compute before effects so value is stable
  const isSignupRoute = pathname.startsWith("/seller/signup");

  // Effect 1: role guard — only for non-signup routes
  useEffect(() => {
    if (isSignupRoute) return;
    if (!loading && (!dbUser || dbUser.role !== "seller")) {
      router.push(dbUser ? "/" : "/login");
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
          router.push("/seller/signup/pending");
        }
      })
      .catch(() => {
        // On error, don't block the UI — allow dashboard to load
      })
      .finally(() => setStatusLoading(false));
  }, [loading, dbUser, token, router, isSignupRoute]);

  // --- All hooks above this line ---

  // Signup routes: render children directly, no wrapper, no guard
  if (isSignupRoute) {
    return <>{children}</>;
  }

  // Loading / auth guard
  if (loading || !dbUser || dbUser.role !== "seller") {
    return (
      <div style={{ padding: "4rem", textAlign: "center", color: "var(--color-neutral-500)" }}>
        Loading…
      </div>
    );
  }

  // Waiting for verification status or redirecting
  if (statusLoading || verificationStatus === null || verificationStatus !== "approved") {
    return (
      <div style={{ padding: "4rem", textAlign: "center", color: "var(--color-neutral-500)" }}>
        Loading…
      </div>
    );
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
