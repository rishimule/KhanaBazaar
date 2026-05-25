"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState } from "react";
import { Link, usePathname, useRouter } from "@/i18n/navigation";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { useCart } from "@/lib/CartContext";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { DeliveryLocationPicker } from "@/components/DeliveryLocationPicker";
import { SearchBar } from "@/components/search/SearchBar";
import NotificationBell from "@/components/NotificationBell";
import LocaleSwitcher from "./LocaleSwitcher";
import styles from "./NavbarTopBar.module.css";

function PinIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  );
}

function ChevronDown() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function CartIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="9" cy="21" r="1" />
      <circle cx="20" cy="21" r="1" />
      <path d="M1 1h4l2.7 13.4a2 2 0 0 0 2 1.6h9.7a2 2 0 0 0 2-1.6L23 6H6" />
    </svg>
  );
}

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
}

export default function NavbarTopBar() {
  const t = useTranslations("Nav");
  const pathname = usePathname();
  const router = useRouter();
  const { cartCount } = useCart();
  const { dbUser, loading, logout } = useAuth();
  const { location } = useDeliveryLocation();
  const [pickerOpen, setPickerOpen] = useState(false);

  const role = dbUser?.role ?? null;

  const navLinks: { href: string; label: string }[] = [
    { href: "/", label: t("home") },
  ];
  if (!loading && !role) navLinks.push({ href: "/sell", label: t("sell") });
  if (!role || role === "customer") {
    navLinks.push({ href: "/products", label: t("products") });
    navLinks.push({ href: "/stores", label: t("stores") });
  }
  if (role === "customer") navLinks.push({ href: "/account/orders", label: t("orders") });

  const handleLogout = async () => {
    await logout();
    router.push("/");
  };

  return (
    <div className={styles.inner}>
      <div className={styles.row1}>
        <Link href="/" className={styles.logo} aria-label="khanabazaar home">
          <span>khanabazaar</span>
          <span className={styles.logoDot} aria-hidden />
        </Link>

        {(!role || role === "customer") && (
          <button
            type="button"
            className={styles.deliverChip}
            onClick={() => setPickerOpen(true)}
            aria-label={t("setDeliveryLocation")}
          >
            <PinIcon />
            <span className={styles.deliverChipText}>
              {location?.label ?? t("setLocation")}
            </span>
            <ChevronDown />
          </button>
        )}
      </div>

      <div className={styles.row2}>
        <SearchBar />
      </div>

      <div className={styles.navLinks}>
        {navLinks.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`${styles.navLink} ${isActive(pathname, link.href) ? styles.navLinkActive : ""}`}
          >
            {link.label}
          </Link>
        ))}
      </div>

      <div className={styles.navActions}>
        {role === "customer" && (
          <Link href="/account" className={styles.actionLink}>
            {t("account")}
          </Link>
        )}

        {(!role || role === "customer") && (
          <Link href="/cart" className={styles.cartBtn} aria-label={t("cartAriaLabel")}>
            <CartIcon />
            <span className={styles.cartLabel}>Cart</span>
            {cartCount > 0 && (
              <span className={styles.cartBadge}>
                {cartCount > 99 ? "99+" : cartCount}
              </span>
            )}
          </Link>
        )}

        {role === "customer" && <NotificationBell />}

        <LocaleSwitcher />

        {!loading && (
          dbUser ? (
            <button
              type="button"
              className={styles.authBtn}
              onClick={handleLogout}
              title={t("logoutTitleSignedIn", {
                who: dbUser.email ?? dbUser.full_name ?? t("drawerUserFallback"),
              })}
            >
              <span className={styles.authAvatar}>
                {(dbUser.full_name ?? dbUser.email ?? "U").charAt(0).toUpperCase()}
              </span>
              <span>{t("logoutLabel")}</span>
            </button>
          ) : (
            <Link href="/login" className={styles.loginBtn}>
              {t("signIn")}
            </Link>
          )
        )}
      </div>

      <DeliveryLocationPicker open={pickerOpen} onClose={() => setPickerOpen(false)} />
    </div>
  );
}
