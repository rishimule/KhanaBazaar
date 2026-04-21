"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { useCart } from "@/lib/CartContext";
import { useAuth } from "@/lib/AuthContext";
import styles from "./Navbar.module.css";

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href);
}

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { cartCount } = useCart();
  const { dbUser, loading, logout } = useAuth();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const role = dbUser?.role ?? null;

  // Build nav links based on role
  const navLinks = [
    { href: "/", label: "Home", icon: "🏠" },
  ];

  if (!loading && (!role || role === "customer")) {
    navLinks.push({ href: "/sell", label: "Sell", icon: "🛍️" });
  }
  if (role === "customer" || role === "seller" || role === "admin") {
    navLinks.push({ href: "/stores", label: "Stores", icon: "🏪" });
  }
  if (role === "seller") {
    navLinks.push({ href: "/seller", label: "Seller", icon: "📊" });
  }
  if (role === "admin") {
    navLinks.push({ href: "/admin", label: "Admin", icon: "⚙️" });
  }

  const handleLogout = async () => {
    await logout();
    router.push("/");
  };

  return (
    <nav className={styles.nav}>
      <div className={styles.navInner}>
        {/* Logo */}
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

        {/* Desktop links */}
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

        {/* Right section */}
        <div className={styles.navActions}>
          {/* Cart — visible to logged-in customers */}
          {dbUser && role === "customer" && (
            <Link href="/cart" className={styles.cartBtn} aria-label="Shopping cart">
              🛒
              {cartCount > 0 && (
                <span className={styles.cartBadge}>{cartCount}</span>
              )}
            </Link>
          )}

          {/* Auth button */}
          {!loading && (
            <>
              {dbUser ? (
                <button
                  className={styles.authBtn}
                  onClick={handleLogout}
                  title={`Signed in as ${dbUser.email ?? dbUser.full_name}`}
                >
                  <span className={styles.authAvatar}>
                    {(dbUser.full_name ?? dbUser.email ?? "U").charAt(0).toUpperCase()}
                  </span>
                  <span className={styles.authLabel}>Logout</span>
                </button>
              ) : (
                <Link href="/login" className={styles.loginBtn}>
                  Sign In
                </Link>
              )}
            </>
          )}

          {/* Mobile hamburger */}
          <button
            className={styles.hamburger}
            onClick={() => setDrawerOpen(true)}
            aria-label="Open menu"
          >
            ☰
          </button>
        </div>
      </div>

      {/* Mobile drawer */}
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
              aria-label="Close menu"
            >
              ✕
            </button>

            {/* User info in drawer */}
            {dbUser && (
              <div className={styles.drawerUser}>
                <span className={styles.drawerUserAvatar}>
                  {(dbUser.full_name ?? dbUser.email ?? "U").charAt(0).toUpperCase()}
                </span>
                <div className={styles.drawerUserInfo}>
                  <span className={styles.drawerUserName}>{dbUser.full_name ?? "User"}</span>
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
            {dbUser && role === "customer" && (
              <Link
                href="/cart"
                className={styles.drawerLink}
                onClick={() => setDrawerOpen(false)}
              >
                🛒 Cart {cartCount > 0 && `(${cartCount})`}
              </Link>
            )}

            <div className={styles.drawerDivider} />
            {dbUser ? (
              <button
                className={styles.drawerLink}
                onClick={() => { handleLogout(); setDrawerOpen(false); }}
              >
                🚪 Sign Out
              </button>
            ) : (
              <Link
                href="/login"
                className={styles.drawerLink}
                onClick={() => setDrawerOpen(false)}
              >
                🔑 Sign In
              </Link>
            )}
          </div>
        </>
      )}
    </nav>
  );
}
