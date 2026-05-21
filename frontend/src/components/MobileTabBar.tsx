"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { useAuth } from "@/lib/AuthContext";
import { useCart } from "@/lib/CartContext";
import { useSearchOverlay } from "@/lib/SearchOverlayContext";
import styles from "./MobileTabBar.module.css";

function HomeIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M3 11.5 12 4l9 7.5" />
      <path d="M5 10v10h14V10" />
    </svg>
  );
}

function StoresIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M3 9 5 4h14l2 5" />
      <path d="M4 9v11h16V9" />
      <path d="M9 20v-6h6v6" />
    </svg>
  );
}

function CartTabIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="9" cy="21" r="1" />
      <circle cx="20" cy="21" r="1" />
      <path d="M1 1h4l2.7 13.4a2 2 0 0 0 2 1.6h9.7a2 2 0 0 0 2-1.6L23 6H6" />
    </svg>
  );
}

function AccountIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21c0-4 4-6 8-6s8 2 8 6" />
    </svg>
  );
}

function isRouteHidden(pathname: string | null): boolean {
  if (!pathname) return false;
  if (pathname === "/login") return true;
  if (pathname.startsWith("/checkout/")) return true;
  return false;
}

function isTabActive(pathname: string | null, href: string): boolean {
  if (!pathname) return false;
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href);
}

export default function MobileTabBar() {
  const t = useTranslations("Nav");
  const pathname = usePathname();
  const { dbUser } = useAuth();
  const { cartCount } = useCart();
  const { open: overlayOpen } = useSearchOverlay();

  if (isRouteHidden(pathname)) return null;

  const accountHref = dbUser ? "/account" : "/login";

  const tabs: { href: string; label: string; icon: React.ReactNode; badge?: number }[] = [
    { href: "/", label: t("tabHome"), icon: <HomeIcon /> },
    { href: "/stores", label: t("tabStores"), icon: <StoresIcon /> },
    { href: "/cart", label: t("tabCart"), icon: <CartTabIcon />, badge: cartCount > 0 ? cartCount : undefined },
    { href: accountHref, label: t("tabAccount"), icon: <AccountIcon /> },
  ];

  return (
    <nav
      className={styles.bar}
      aria-label="Primary"
      data-overlay-open={overlayOpen ? "true" : "false"}
    >
      {tabs.map((tab) => {
        const active = isTabActive(pathname, tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`${styles.tab} ${active ? styles.tabActive : ""}`}
            aria-current={active ? "page" : undefined}
          >
            <span className={styles.icon}>
              {tab.icon}
              {tab.badge !== undefined && <span className={styles.badge}>{tab.badge}</span>}
            </span>
            <span className={styles.label}>{tab.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
