"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";
import { useCart } from "@/lib/CartContext";
import { useAuth } from "@/lib/AuthContext";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { DeliveryLocationPicker } from "@/components/DeliveryLocationPicker";
import LocaleSwitcher from "./LocaleSwitcher";
import styles from "./Navbar.module.css";

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href);
}

function SearchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
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

function MenuIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <line x1="3" y1="6"  x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  );
}

function BackIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <polyline points="15 18 9 12 15 6" />
    </svg>
  );
}

type NavbarVariant = "auto" | "signup" | "dashboard";

export default function Navbar({ variant = "auto" }: { variant?: NavbarVariant } = {}) {
  const t = useTranslations("Nav");
  const pathname = usePathname();
  const router = useRouter();
  const { cartCount } = useCart();
  const { dbUser, loading, logout } = useAuth();
  const { location } = useDeliveryLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

  const role = dbUser?.role ?? null;

  const effectiveVariant: "customer" | "operator-stripped" | "signup" | "dashboard" =
    variant === "signup"
      ? "signup"
      : variant === "dashboard"
        ? "dashboard"
        : role === "seller" || role === "admin"
          ? "operator-stripped"
          : "customer";

  const navLinks: { href: string; label: string }[] = [
    { href: "/", label: t("home") },
  ];

  if (!loading && !role) {
    navLinks.push({ href: "/sell", label: t("sell") });
  }
  if (!role || role === "customer") {
    navLinks.push({ href: "/stores", label: t("stores") });
  }
  if (role === "customer") {
    navLinks.push({ href: "/account/orders", label: t("orders") });
  }

  const handleLogout = async () => {
    await logout();
    router.push("/");
  };

  if (effectiveVariant === "operator-stripped") {
    const dashboardHref = role === "admin" ? "/admin" : "/seller";
    return (
      <nav className={styles.nav}>
        <div className={styles.navInnerStripped}>
          <Link href={dashboardHref} className={styles.logo} aria-label="khanabazaar dashboard">
            <span>khanabazaar</span>
            <span className={styles.logoDot} aria-hidden />
          </Link>
          <span className={styles.strippedSpacer} />
          <Link
            href={dashboardHref}
            className={styles.backToDashboard}
            aria-label={t("backToDashboard")}
          >
            <BackIcon />
            <span className={styles.backToDashboardLabel}>{t("backToDashboard")}</span>
          </Link>
          <LocaleSwitcher />
          {!loading && dbUser && (
            <button
              className={styles.authBtn}
              onClick={handleLogout}
              title={t("logoutTitleSignedIn", { who: dbUser.email ?? dbUser.full_name ?? "" })}
            >
              <span className={styles.authAvatar}>
                {(dbUser.full_name ?? dbUser.email ?? "U").charAt(0).toUpperCase()}
              </span>
              <span>{t("logoutLabel")}</span>
            </button>
          )}
        </div>
      </nav>
    );
  }

  if (effectiveVariant === "dashboard") {
    const dashboardHref = role === "admin" ? "/admin" : "/seller";
    return (
      <nav className={styles.nav}>
        <div className={styles.navInnerStripped}>
          <Link href={dashboardHref} className={styles.logo} aria-label="khanabazaar dashboard">
            <span>khanabazaar</span>
            <span className={styles.logoDot} aria-hidden />
          </Link>
          <span className={styles.strippedSpacer} />
          {!loading && dbUser && (
            <button
              className={styles.authBtn}
              onClick={handleLogout}
              title={t("logoutTitleSignedIn", { who: dbUser.email ?? dbUser.full_name ?? "" })}
            >
              <span className={styles.authAvatar}>
                {(dbUser.full_name ?? dbUser.email ?? "U").charAt(0).toUpperCase()}
              </span>
              <span>{t("logoutLabel")}</span>
            </button>
          )}
        </div>
      </nav>
    );
  }

  if (effectiveVariant === "signup") {
    return (
      <nav className={styles.nav}>
        <div className={styles.navInnerStripped}>
          <Link href="/" className={styles.logo} aria-label="khanabazaar home">
            <span>khanabazaar</span>
            <span className={styles.logoDot} aria-hidden />
          </Link>
          <span className={styles.strippedSpacer} />
          <LocaleSwitcher />
          <Link href="/login" className={styles.loginBtn}>
            {t("signIn")}
          </Link>
        </div>
      </nav>
    );
  }

  return (
    <nav className={styles.nav}>
      <div className={styles.navInner}>
        <Link href="/" className={styles.logo} aria-label="khanabazaar home">
          <span>khanabazaar</span>
          <span className={styles.logoDot} aria-hidden />
        </Link>

        {(!role || role === "customer") && (
          <button
            type="button"
            className={styles.deliverChip}
            onClick={() => setPickerOpen(true)}
            aria-label="Set delivery location"
          >
            <PinIcon />
            <span className={styles.deliverChipText}>
              {location?.label ?? "Set location"}
            </span>
            <ChevronDown />
          </button>
        )}

        <div className={styles.searchWrap}>
          <span className={styles.searchIcon}><SearchIcon /></span>
          <input
            className={styles.searchInput}
            type="search"
            placeholder="Search ramen, dragon fruit, kimchi…"
            aria-label="Search products"
          />
        </div>

        <div className={styles.navLinks}>
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`${styles.navLink} ${
                isActive(pathname, link.href) ? styles.navLinkActive : ""
              }`}
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
              {cartCount > 0 && <span className={styles.cartBadge}>{cartCount}</span>}
            </Link>
          )}

          <LocaleSwitcher />

          {!loading && (
            <>
              {dbUser ? (
                <button
                  className={styles.authBtn}
                  onClick={handleLogout}
                  title={t("logoutTitleSignedIn", { who: dbUser.email ?? dbUser.full_name ?? "" })}
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
              )}
            </>
          )}

          <button
            className={styles.hamburger}
            onClick={() => setDrawerOpen(true)}
            aria-label={t("openMenu")}
          >
            <MenuIcon />
          </button>
        </div>
      </div>

      {drawerOpen && (
        <>
          <div
            className={styles.overlay}
            onClick={() => setDrawerOpen(false)}
          />
          <div className={styles.drawer}>
            <button
              className={styles.drawerClose}
              onClick={() => setDrawerOpen(false)}
              aria-label={t("closeMenu")}
            >
              ✕
            </button>

            {dbUser && (
              <div className={styles.drawerUser}>
                <span className={styles.drawerUserAvatar}>
                  {(dbUser.full_name ?? dbUser.email ?? "U").charAt(0).toUpperCase()}
                </span>
                <div className={styles.drawerUserInfo}>
                  <span className={styles.drawerUserName}>
                    {dbUser.full_name ?? t("drawerUserFallback")}
                  </span>
                  <span className={styles.drawerUserRole}>{dbUser.role}</span>
                </div>
              </div>
            )}

            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={`${styles.drawerLink} ${
                  isActive(pathname, link.href) ? styles.drawerLinkActive : ""
                }`}
                onClick={() => setDrawerOpen(false)}
              >
                {link.label}
              </Link>
            ))}
            {(!role || role === "customer") && (
              <Link
                href="/cart"
                className={styles.drawerLink}
                onClick={() => setDrawerOpen(false)}
              >
                {t("drawerCart")} {cartCount > 0 && `(${cartCount})`}
              </Link>
            )}

            <div className={styles.drawerDivider} />
            {dbUser ? (
              <button
                className={styles.drawerLink}
                onClick={() => { handleLogout(); setDrawerOpen(false); }}
              >
                {t("drawerSignOut")}
              </button>
            ) : (
              <Link
                href="/login"
                className={styles.drawerLink}
                onClick={() => setDrawerOpen(false)}
              >
                {t("drawerSignIn")}
              </Link>
            )}
          </div>
        </>
      )}

      <DeliveryLocationPicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
      />
    </nav>
  );
}
