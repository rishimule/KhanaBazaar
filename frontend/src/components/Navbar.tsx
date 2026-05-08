"use client";

import Link from "next/link";
import Image from "next/image";
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

export default function Navbar() {
  const t = useTranslations("Nav");
  const pathname = usePathname();
  const router = useRouter();
  const { cartCount } = useCart();
  const { dbUser, loading, logout } = useAuth();
  const { location } = useDeliveryLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

  const role = dbUser?.role ?? null;

  const navLinks: { href: string; label: string; icon: string }[] = [
    { href: "/", label: t("home"), icon: "🏠" },
  ];

  if (!loading && (!role || role === "customer")) {
    navLinks.push({ href: "/sell", label: t("sell"), icon: "🛍️" });
  }
  if (role === "customer" || role === "seller" || role === "admin") {
    navLinks.push({ href: "/stores", label: t("stores"), icon: "🏪" });
  }
  if (role === "customer") {
    navLinks.push({ href: "/account/orders", label: t("orders"), icon: "📦" });
    navLinks.push({ href: "/account", label: t("account"), icon: "👤" });
  }
  if (role === "seller") {
    navLinks.push({ href: "/seller", label: t("seller"), icon: "📊" });
  }
  if (role === "admin") {
    navLinks.push({ href: "/admin", label: t("admin"), icon: "⚙️" });
  }

  const handleLogout = async () => {
    await logout();
    router.push("/");
  };

  return (
    <nav className={styles.nav}>
      <div className={styles.navInner}>
        <Link href="/" className={styles.logo}>
          <span className={styles.logoIcon}>
            <Image
              src="/icons/icon-192x192.png"
              alt="Khana Bazaar"
              width={32}
              height={32}
            />
          </span>
          <span>
            Khana<span className={styles.logoAccent}>Bazaar</span>
          </span>
        </Link>

        <div className={styles.navLinks}>
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`${styles.navLink} ${
                isActive(pathname, link.href) ? styles.navLinkActive : ""
              }`}
            >
              {link.icon} {link.label}
            </Link>
          ))}
        </div>

        <div className={styles.navActions}>
          {(!role || role === "customer") && (
            <button
              type="button"
              className={styles.deliverChip}
              onClick={() => setPickerOpen(true)}
              aria-label="Set delivery location"
            >
              📍 <span className={styles.deliverChipText}>
                {location?.label ?? "Set location"}
              </span>
            </button>
          )}

          {(!role || role === "customer") && (
            <Link href="/cart" className={styles.cartBtn} aria-label={t("cartAriaLabel")}>
              🛒
              {cartCount > 0 && (
                <span className={styles.cartBadge}>{cartCount}</span>
              )}
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
                  <span className={styles.authLabel}>{t("logoutLabel")}</span>
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
            ☰
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
                className={styles.drawerLink}
                onClick={() => setDrawerOpen(false)}
              >
                {link.icon} {link.label}
              </Link>
            ))}
            {(!role || role === "customer") && (
              <Link
                href="/cart"
                className={styles.drawerLink}
                onClick={() => setDrawerOpen(false)}
              >
                🛒 {t("drawerCart")} {cartCount > 0 && `(${cartCount})`}
              </Link>
            )}

            <div className={styles.drawerDivider} />
            {dbUser ? (
              <button
                className={styles.drawerLink}
                onClick={() => { handleLogout(); setDrawerOpen(false); }}
              >
                🚪 {t("drawerSignOut")}
              </button>
            ) : (
              <Link
                href="/login"
                className={styles.drawerLink}
                onClick={() => setDrawerOpen(false)}
              >
                🔑 {t("drawerSignIn")}
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
