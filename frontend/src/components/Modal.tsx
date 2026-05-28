"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import styles from "./Modal.module.css";

type ModalSize = "default" | "wide" | "sheet";

interface Props {
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  onClose: () => void;
  /** "default" = 500px max-width (existing behavior), "wide" = 720px for
   *  rich content, "sheet" = slide-up bottom-sheet on mobile (centered on tablet+). */
  size?: ModalSize;
}

export default function Modal({ title, children, footer, onClose, size = "default" }: Props) {
  const t = useTranslations("Shared");
  const [mounted, setMounted] = useState(false);

  // Mount + portal-ready (SSR safety) + Escape close + body scroll lock so
  // the page (and sidebar) underneath can't be interacted with while a modal
  // is open. Portaling to <body> escapes any parent stacking context that
  // would otherwise let the dashboard sidebar paint on top of the scrim.
  useEffect(() => {
    setMounted(true);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  if (!mounted) return null;

  return createPortal(
    <div className={styles.backdrop} onClick={onClose}>
      <div
        className={[
          styles.modal,
          size === "wide" && styles.modalWide,
          size === "sheet" && styles.modalSheet,
        ]
          .filter(Boolean)
          .join(" ")}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className={styles.header}>
          <h2 className={styles.title}>{title}</h2>
          <button
            className={styles.closeBtn}
            onClick={onClose}
            aria-label={t("modal.close")}
          >
            ✕
          </button>
        </div>
        <div className={styles.body}>{children}</div>
        {footer && <div className={styles.footer}>{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

// Re-export form styles for convenience
export { styles as modalStyles };
