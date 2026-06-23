"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
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
  const dialogRef = useRef<HTMLDivElement>(null);

  const FOCUSABLE =
    'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

  // Mount + portal-ready (SSR safety) + Escape close + body scroll lock so
  // the page (and sidebar) underneath can't be interacted with while a modal
  // is open. Portaling to <body> escapes any parent stacking context that
  // would otherwise let the dashboard sidebar paint on top of the scrim.
  // Also traps Tab within the dialog and restores focus to the trigger on close.
  useEffect(() => {
    setMounted(true);
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key === "Tab" && dialogRef.current) {
        const focusables =
          dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE);
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      document.body.style.overflow = prevOverflow;
      previouslyFocused?.focus?.();
    };
  }, [onClose]);

  // Move focus into the dialog once its portal content exists.
  useEffect(() => {
    if (!mounted) return;
    const node = dialogRef.current;
    if (!node) return;
    const first = node.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? node).focus();
  }, [mounted]);

  if (!mounted) return null;

  return createPortal(
    <div className={styles.backdrop} onClick={onClose}>
      <div
        ref={dialogRef}
        tabIndex={-1}
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
