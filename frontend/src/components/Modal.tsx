"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect } from "react";
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
  // Close on Escape key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
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
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        <div className={styles.body}>{children}</div>
        {footer && <div className={styles.footer}>{footer}</div>}
      </div>
    </div>
  );
}

// Re-export form styles for convenience
export { styles as modalStyles };
