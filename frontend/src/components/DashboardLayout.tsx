"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslations } from "next-intl";
import Avatar from "@/components/Avatar";
import styles from "./DashboardLayout.module.css";

interface NavItem {
  href: string;
  label: string;
  icon: string;
}

type DashboardRole = "seller" | "admin" | "customer";

interface Props {
  children: React.ReactNode;
  role: DashboardRole;
  roleName: string;
  title: string;
  navItems: NavItem[];
  footer?: React.ReactNode;
  avatarUrl?: string | null;
}

const ROLE_LABEL_KEYS: Record<DashboardRole, string> = {
  seller: "roleSellerLabel",
  admin: "roleAdminLabel",
  customer: "roleCustomerLabel",
};

const ROLE_ICONS: Record<DashboardRole, string> = {
  seller: "🏪",
  admin: "⚙️",
  customer: "👤",
};

const ROLE_ICON_CLASSES: Record<DashboardRole, string> = {
  seller: styles.roleIconSeller,
  admin: styles.roleIconAdmin,
  customer: styles.roleIconCustomer,
};

export default function DashboardLayout({
  children,
  role,
  roleName,
  title,
  navItems,
  footer,
  avatarUrl,
}: Props) {
  const t = useTranslations("Dashboard");
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const sidebar = (
    <>
      {sidebarOpen && (
        <div className={styles.overlay} onClick={() => setSidebarOpen(false)} />
      )}
      <aside
        className={`${styles.sidebar} ${sidebarOpen ? styles.sidebarOpen : ""}`}
      >
        <div className={styles.sidebarHeader}>
          <div
            className={`${styles.roleIcon} ${ROLE_ICON_CLASSES[role]}`}
          >
            {avatarUrl ? (
              <Avatar avatarUrl={avatarUrl} name={roleName} seed={roleName} size={40} />
            ) : (
              ROLE_ICONS[role]
            )}
          </div>
          <div className={styles.roleInfo}>
            <span className={styles.roleName}>{roleName}</span>
            <span className={styles.roleLabel}>{t(ROLE_LABEL_KEYS[role])}</span>
          </div>
        </div>

        <nav className={styles.sidebarNav}>
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`${styles.sidebarLink} ${
                pathname === item.href ? styles.sidebarLinkActive : ""
              }`}
              onClick={() => setSidebarOpen(false)}
            >
              <span className={styles.sidebarLinkIcon}>{item.icon}</span>
              {item.label}
            </Link>
          ))}
        </nav>
        {footer && <div className={styles.sidebarFooter}>{footer}</div>}
      </aside>
    </>
  );

  return (
    <div className={styles.dashboard}>
      {mounted && createPortal(sidebar, document.body)}

      <div className={styles.main}>
        <div className={styles.topBar}>
          <div className={styles.topBarActions}>
            <button
              className={styles.mobileToggle}
              onClick={() => setSidebarOpen(true)}
              aria-label={t("openSidebar")}
            >
              ☰
            </button>
            <h1 className={styles.topBarTitle}>{title}</h1>
          </div>
        </div>
        <div className={styles.content}>{children}</div>
      </div>
    </div>
  );
}
