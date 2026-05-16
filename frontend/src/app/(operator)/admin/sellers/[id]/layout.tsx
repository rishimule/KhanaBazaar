"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import ImpersonationBanner from "@/components/admin/ImpersonationBanner";
import { useAuth } from "@/lib/AuthContext";
import { fetchSellerHub } from "@/lib/adminActions";
import type { SellerHubSummary } from "@/types";
import styles from "./layout.module.css";

const TABS: { slug: string; label: string }[] = [
  { slug: "profile", label: "Profile" },
  { slug: "products", label: "Products" },
  { slug: "orders", label: "Orders" },
  { slug: "activity", label: "Activity" },
];

export default function SellerHubLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const pathname = usePathname();
  const { token, dbUser, loading } = useAuth();
  const [hub, setHub] = useState<SellerHubSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // The parent /admin/layout.tsx already gates non-admins; this layout just
  // loads the per-seller header data.
  useEffect(() => {
    if (loading || !dbUser || dbUser.role !== "admin" || !token) return;
    fetchSellerHub(Number(id), token)
      .then(setHub)
      .catch(() => setErr("Failed to load seller"));
  }, [id, token, dbUser, loading]);

  // Determine active tab from pathname.
  const segments = pathname.split("/").filter(Boolean);
  const activeSlug = segments[segments.length - 1];
  const isActivityTab = activeSlug === "activity";

  if (err) {
    return (
      <div className={styles.error}>
        {err} —{" "}
        <button onClick={() => router.push("/admin/sellers")}>back</button>
      </div>
    );
  }
  if (!hub) {
    return (
      <div className={styles.loading}>Loading seller…</div>
    );
  }

  return (
    <div className={styles.wrap}>
      <ImpersonationBanner
        businessName={hub.business_name}
        verificationStatus={hub.verification_status}
        variant={isActivityTab ? "viewing" : "acting"}
      />
      <div className={styles.tabs}>
        {TABS.map((t) => {
          const href = `/admin/sellers/${id}/${t.slug}`;
          const active = activeSlug === t.slug;
          return (
            <Link
              key={t.slug}
              href={href}
              className={active ? styles.tabActive : styles.tab}
            >
              {t.label}
            </Link>
          );
        })}
      </div>
      <div className={styles.content}>{children}</div>
    </div>
  );
}
