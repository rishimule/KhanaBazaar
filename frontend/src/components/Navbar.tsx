"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import LocaleSwitcher from "./LocaleSwitcher";
import MobileTabBar from "./MobileTabBar";
import NavbarTopBar from "./NavbarTopBar";
import styles from "./Navbar.module.css";

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
  const router = useRouter();
  const { dbUser, loading, logout } = useAuth();

  const role = dbUser?.role ?? null;

  const effectiveVariant: "customer" | "operator-stripped" | "signup" | "dashboard" =
    variant === "signup"
      ? "signup"
      : variant === "dashboard"
        ? "dashboard"
        : role === "seller" || role === "admin"
          ? "operator-stripped"
          : "customer";

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
    <>
      <nav className={styles.nav}>
        <NavbarTopBar />
      </nav>
      <MobileTabBar />
    </>
  );
}
