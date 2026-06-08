"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import LogoutConfirmDialog from "@/components/LogoutConfirmDialog";
import { useLogoutConfirm } from "@/lib/useLogoutConfirm";
import styles from "./SidebarFooter.module.css";

export default function AccountSidebarFooter() {
  const t = useTranslations("Account");
  const router = useRouter();
  const { open, openDialog, closeDialog } = useLogoutConfirm();

  return (
    <>
      <button
        type="button"
        className={styles.logoutBtn}
        onClick={openDialog}
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <span className={styles.icon} aria-hidden>🚪</span>
        {t("navLogout")}
      </button>
      {/* Land on /login: the account layout guard redirects there on a null
          user anyway, so matching it keeps the farewell race-free. */}
      {open && (
        <LogoutConfirmDialog onClose={closeDialog} onRedirect={() => router.push("/login")} />
      )}
    </>
  );
}
