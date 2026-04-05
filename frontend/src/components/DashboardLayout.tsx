"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import styles from "./DashboardLayout.module.css";

interface NavItem {
  href: string;
  label: string;
  icon: string;
}

interface Props {
  children: React.ReactNode;
  role: "seller" | "admin";
  roleName: string;
  title: string;
  navItems: NavItem[];
}

export default function DashboardLayout({
  children,
  role,
  roleName,
  title,
  navItems,
}: Props) {
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className={styles.dashboard}>
      {/* Sidebar */}
      {sidebarOpen && (
        <div className={styles.overlay} onClick={() => setSidebarOpen(false)} />
      )}
      <aside
        className={`${styles.sidebar} ${sidebarOpen ? styles.sidebarOpen : ""}`}
      >
        <div className={styles.sidebarHeader}>
          <div
            className={`${styles.roleIcon} ${
              role === "seller" ? styles.roleIconSeller : styles.roleIconAdmin
            }`}
          >
            {role === "seller" ? "🏪" : "⚙️"}
          </div>
          <div className={styles.roleInfo}>
            <span className={styles.roleName}>{roleName}</span>
            <span className={styles.roleLabel}>
              {role === "seller" ? "Seller Portal" : "Admin Panel"}
            </span>
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
      </aside>

      {/* Main */}
      <div className={styles.main}>
        <div className={styles.topBar}>
          <div className={styles.topBarActions}>
            <button
              className={styles.mobileToggle}
              onClick={() => setSidebarOpen(true)}
              aria-label="Open sidebar"
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
