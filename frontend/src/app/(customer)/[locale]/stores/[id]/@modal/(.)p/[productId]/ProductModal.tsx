"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import styles from "./ProductModal.module.css";

interface Props {
  storeUrl: string;
  closeLabel: string;
  children: ReactNode;
}

export default function ProductModal({ storeUrl, closeLabel, children }: Props) {
  const router = useRouter();

  const close = () => {
    if (typeof window !== "undefined" && window.history.length > 1) {
      router.back();
    } else {
      router.push(storeUrl);
    }
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      // A fullscreen image viewer (yet-another-react-lightbox) can be layered
      // above this modal. Its Escape handler runs as a React synthetic event and
      // cannot stop this native document listener, so let it close the viewer
      // first instead of tearing down the whole product modal in one keystroke.
      if (document.querySelector(".yarl__portal_open")) return;
      close();
    };
    document.addEventListener("keydown", handler);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handler);
      document.body.style.overflow = previousOverflow;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className={styles.backdrop} onClick={close}>
      <div
        className={styles.sheet}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <button
          type="button"
          className={styles.close}
          onClick={close}
          aria-label={closeLabel}
        >
          ✕
        </button>
        {children}
      </div>
    </div>
  );
}
