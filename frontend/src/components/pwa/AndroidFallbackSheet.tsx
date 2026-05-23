"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useTranslations } from "next-intl";
import Modal from "@/components/Modal";
import styles from "./pwa-install.module.css";

export default function AndroidFallbackSheet({ onClose }: { onClose: () => void }) {
  const t = useTranslations("PWAInstall.fallbackSheet");
  return (
    <Modal
      title={t("title")}
      size="sheet"
      onClose={onClose}
      footer={
        <button type="button" className={styles.dismissBtn} onClick={onClose}>
          {t("dismiss")}
        </button>
      }
    >
      <p className={styles.fallbackBody}>{t("body")}</p>
    </Modal>
  );
}
