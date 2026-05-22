"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import Modal from "@/components/Modal";
import { useAuth } from "@/lib/AuthContext";
import styles from "./SidebarFooter.module.css";

export default function AccountSidebarFooter() {
  const t = useTranslations("Account");
  const router = useRouter();
  const { logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);

  const handleConfirm = async () => {
    setPending(true);
    await logout();
    router.push("/");
  };

  const handleClose = () => {
    if (!pending) setOpen(false);
  };

  return (
    <>
      <button
        type="button"
        className={styles.logoutBtn}
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
      >
        <span className={styles.icon} aria-hidden>🚪</span>
        {t("navLogout")}
      </button>
      {open && (
        <Modal
          title={t("logoutConfirmTitle")}
          onClose={handleClose}
          footer={
            <>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={pending}
                onClick={handleClose}
              >
                {t("logoutCancel")}
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={pending}
                onClick={handleConfirm}
                autoFocus
              >
                {t("logoutConfirmCta")}
              </button>
            </>
          }
        >
          <p className={styles.modalBody}>{t("logoutConfirmBody")}</p>
        </Modal>
      )}
    </>
  );
}
