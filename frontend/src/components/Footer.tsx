// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import Link from "next/link";
import { useTranslations } from "next-intl";
import styles from "./Footer.module.css";

export default function Footer() {
  const t = useTranslations("Footer");
  return (
    <footer className={styles.footer}>
      <div className={styles.footerInner}>
        <div className={styles.footerBrand}>
          <div className={styles.footerLogo}>
            <span>khanabazaar</span>
            <span className={styles.footerLogoAccent} aria-hidden />
          </div>
          <p className={styles.footerDescription}>{t("tagline")}</p>
        </div>

        <div className={styles.footerColumn}>
          <span className={styles.footerColumnTitle}>{t("quickLinks")}</span>
          <Link href="/" className={styles.footerLink}>
            {t("home")}
          </Link>
          <Link href="/stores" className={styles.footerLink}>
            {t("browseStores")}
          </Link>
          <Link href="/cart" className={styles.footerLink}>
            {t("myCart")}
          </Link>
        </div>

        <div className={styles.footerColumn}>
          <span className={styles.footerColumnTitle}>{t("company")}</span>
          <Link href="/about" className={styles.footerLink}>
            {t("aboutUs")}
          </Link>
          <Link href="/sell" className={styles.footerLink}>
            {t("forSellers")}
          </Link>
          <Link href="/privacy" className={styles.footerLink}>
            {t("privacy")}
          </Link>
          <Link href="/terms" className={styles.footerLink}>
            {t("terms")}
          </Link>
        </div>
      </div>

      <div className={styles.footerBottom}>
        <span>{t("copyright", { year: new Date().getFullYear() })}</span>
        <span className={styles.madeWith}>{t("madeWith")}</span>
      </div>
    </footer>
  );
}
