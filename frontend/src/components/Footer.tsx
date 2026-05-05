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
            Khana<span className={styles.footerLogoAccent}>Bazaar</span>
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
          <span className={styles.footerLink}>{t("aboutUs")}</span>
          <Link href="/sell" className={styles.footerLink}>
            {t("forSellers")}
          </Link>
          <span className={styles.footerLink}>{t("privacy")}</span>
          <span className={styles.footerLink}>{t("terms")}</span>
        </div>
      </div>

      <div className={styles.footerBottom}>
        <span>{t("copyright", { year: new Date().getFullYear() })}</span>
        <span className={styles.madeWith}>{t("madeWith")}</span>
      </div>
    </footer>
  );
}
