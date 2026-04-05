"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useCart } from "@/lib/CartContext";
import styles from "./Navbar.module.css";

const NAV_LINKS = [
  { href: "/", label: "Home", icon: "🏠" },
  { href: "/stores", label: "Stores", icon: "🏪" },
  { href: "/seller", label: "Seller", icon: "📊" },
  { href: "/admin", label: "Admin", icon: "⚙️" },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href);
}

export default function Navbar() {
  const pathname = usePathname();
  const { cartCount } = useCart();
  const [drawerOpen, setDrawerOpen] = useState(false);

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
          {NAV_LINKS.map((link) => (
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
          <Link href="/cart" className={styles.cartBtn} aria-label="Shopping cart">
            🛒
            {cartCount > 0 && (
              <span className={styles.cartBadge}>{cartCount}</span>
            )}
          </Link>

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
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={styles.drawerLink}
                onClick={() => setDrawerOpen(false)}
              >
                {link.icon} {link.label}
              </Link>
            ))}
            <Link
              href="/cart"
              className={styles.drawerLink}
              onClick={() => setDrawerOpen(false)}
            >
              🛒 Cart {cartCount > 0 && `(${cartCount})`}
            </Link>
          </div>
        </>
      )}
    </nav>
  );
}
