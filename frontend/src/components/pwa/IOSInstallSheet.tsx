"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useTranslations } from "next-intl";
import Modal from "@/components/Modal";
import styles from "./pwa-install.module.css";

const ShareGlyph = (
  <svg viewBox="0 0 24 24" width="22" height="22">
    <path
      fill="currentColor"
      d="M12 3l-4 4h3v8h2V7h3l-4-4zm-7 8v8a2 2 0 002 2h10a2 2 0 002-2v-8h-2v8H7v-8H5z"
    />
  </svg>
);

const AddSquareGlyph = (
  <svg viewBox="0 0 24 24" width="22" height="22">
    <path
      fill="currentColor"
      d="M5 3a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2V5a2 2 0 00-2-2H5zm6 4h2v4h4v2h-4v4h-2v-4H7v-2h4V7z"
    />
  </svg>
);

const CheckGlyph = (
  <svg viewBox="0 0 24 24" width="22" height="22">
    <path
      fill="currentColor"
      d="M9 16.2L4.8 12l-1.4 1.4L9 19l12-12-1.4-1.4z"
    />
  </svg>
);

export default function IOSInstallSheet({ onClose }: { onClose: () => void }) {
  const t = useTranslations("PWAInstall.iosSheet");
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
      <p className={styles.subtitle}>{t("subtitle")}</p>
      <ol className={styles.stepList} role="list">
        <li className={styles.step}>
          <span className={styles.stepNumber} aria-hidden="true">1</span>
          <span className={styles.stepGlyph} aria-hidden="true">{ShareGlyph}</span>
          <span className={styles.stepText}>{t("step1")}</span>
        </li>
        <li className={styles.step}>
          <span className={styles.stepNumber} aria-hidden="true">2</span>
          <span className={styles.stepGlyph} aria-hidden="true">{AddSquareGlyph}</span>
          <span className={styles.stepText}>{t("step2")}</span>
        </li>
        <li className={styles.step}>
          <span className={styles.stepNumber} aria-hidden="true">3</span>
          <span className={styles.stepGlyph} aria-hidden="true">{CheckGlyph}</span>
          <span className={styles.stepText}>{t("step3")}</span>
        </li>
      </ol>
      <p className={styles.footnote}>{t("footnote")}</p>
    </Modal>
  );
}
