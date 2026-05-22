"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useState } from "react";
import { createPortal } from "react-dom";
import { useTranslations } from "next-intl";
import Modal from "@/components/Modal";
import { useAuth } from "@/lib/AuthContext";
import styles from "./SidebarFooter.module.css";

export default function AccountSidebarFooter() {
  const t = useTranslations("Account");
  const { logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);

  const handleConfirm = async () => {
    setPending(true);
    try {
      await logout();
    } finally {
      setPending(false);
    }
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
        aria-expanded={open}
      >
        <span className={styles.icon} aria-hidden>🚪</span>
        {t("navLogout")}
      </button>
      {open &&
        createPortal(
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
          </Modal>,
          document.body,
        )}
    </>
  );
}
