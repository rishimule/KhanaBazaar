"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import ImpersonationBanner from "@/components/admin/ImpersonationBanner";
import { useAuth } from "@/lib/AuthContext";
import { fetchSellerHub } from "@/lib/adminActions";
import { adminListSellerCRs } from "@/lib/changeRequests";
import type { SellerHubSummary } from "@/types";
import styles from "./layout.module.css";

const TABS: { slug: string; labelKey: string }[] = [
  { slug: "profile", labelKey: "tab.profile" },
  { slug: "products", labelKey: "tab.products" },
  { slug: "orders", labelKey: "tab.orders" },
  { slug: "requests", labelKey: "tab.requests" },
  { slug: "fees", labelKey: "tab.fees" },
  { slug: "credits", labelKey: "tab.credits" },
  { slug: "activity", labelKey: "tab.activity" },
  { slug: "qr", labelKey: "tab.qr" },
];

export default function SellerHubLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const t = useTranslations("Admin.sellerHub");
  const tc = useTranslations("Admin.common");
  const router = useRouter();
  const pathname = usePathname();
  const { token, dbUser, loading } = useAuth();
  const [hub, setHub] = useState<SellerHubSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [openCRCount, setOpenCRCount] = useState<number>(0);

  // The parent /admin/layout.tsx already gates non-admins; this layout just
  // loads the per-seller header data.
  useEffect(() => {
    if (loading || !dbUser || dbUser.role !== "admin" || !token) return;
    fetchSellerHub(Number(id), token)
      .then(setHub)
      .catch(() => setErr(t("loadSellerError")));
  }, [id, token, dbUser, loading, t]);

  // Best-effort open-CR count for the subnav badge. Silently swallow errors
  // so a transient API failure never blocks the per-seller page.
  useEffect(() => {
    if (loading || !dbUser || dbUser.role !== "admin" || !token) return;
    let cancelled = false;
    adminListSellerCRs(token, Number(id), "open")
      .then((rows) => {
        if (!cancelled) setOpenCRCount(rows.length);
      })
      .catch(() => {
        if (!cancelled) setOpenCRCount(0);
      });
    return () => {
      cancelled = true;
    };
  }, [id, token, dbUser, loading]);

  // Determine active tab from pathname. We match on the segment immediately
  // after the seller id so nested routes (e.g. /requests/[crId]) still
  // highlight the parent tab.
  const segments = pathname.split("/").filter(Boolean);
  const idIdx = segments.indexOf(id);
  const activeSlug =
    idIdx >= 0 && segments.length > idIdx + 1
      ? segments[idIdx + 1]
      : segments[segments.length - 1];
  const isActivityTab = activeSlug === "activity";

  if (err) {
    return (
      <div className={styles.error}>
        {err} —{" "}
        <button onClick={() => router.push("/admin/sellers")}>{tc("back")}</button>
      </div>
    );
  }
  if (!hub) {
    return (
      <div className={styles.loading}>{t("loadingSeller")}</div>
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
        {TABS.map((tab) => {
          const href = `/admin/sellers/${id}/${tab.slug}`;
          const active = activeSlug === tab.slug;
          const showBadge = tab.slug === "requests" && openCRCount > 0;
          return (
            <Link
              key={tab.slug}
              href={href}
              className={active ? styles.tabActive : styles.tab}
            >
              {t(tab.labelKey)}
              {showBadge && (
                <span className={styles.badge} aria-label={`${openCRCount} open`}>
                  {openCRCount}
                </span>
              )}
            </Link>
          );
        })}
      </div>
      <div className={styles.content}>{children}</div>
    </div>
  );
}
