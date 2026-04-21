import Link from "next/link";
import styles from "./Footer.module.css";

export default function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={styles.footerInner}>
        {/* Brand */}
        <div className={styles.footerBrand}>
          <div className={styles.footerLogo}>
            Khana<span className={styles.footerLogoAccent}>Bazaar</span>
          </div>
          <p className={styles.footerDescription}>
            Your neighbourhood stores, now at your fingertips. Shop fresh
            groceries &amp; essentials from local sellers and pay instantly with
            UPI.
          </p>
        </div>

        {/* Quick Links */}
        <div className={styles.footerColumn}>
          <span className={styles.footerColumnTitle}>Quick Links</span>
          <Link href="/" className={styles.footerLink}>
            Home
          </Link>
          <Link href="/stores" className={styles.footerLink}>
            Browse Stores
          </Link>
          <Link href="/cart" className={styles.footerLink}>
            My Cart
          </Link>
        </div>

        {/* Company */}
        <div className={styles.footerColumn}>
          <span className={styles.footerColumnTitle}>Company</span>
          <span className={styles.footerLink}>About Us</span>
          <Link href="/sell" className={styles.footerLink}>
            For Sellers
          </Link>
          <span className={styles.footerLink}>Privacy Policy</span>
          <span className={styles.footerLink}>Terms of Service</span>
        </div>
      </div>

      {/* Bottom bar */}
      <div className={styles.footerBottom}>
        <span>
          © {new Date().getFullYear()} Khana Bazaar. All rights reserved.
        </span>
        <span className={styles.madeWith}>
          Made with 🧡 for India&apos;s local sellers
        </span>
      </div>
    </footer>
  );
}
