"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslations } from "next-intl";
import Modal from "@/components/Modal";
import { useAuth } from "@/lib/AuthContext";
import styles from "./LogoutConfirmDialog.module.css";

const FAREWELL_HOLD_MS = 1500;

interface Props {
  /** Cancel / dismiss during the confirm phase. */
  onClose: () => void;
  /** Called after the farewell hold. The consumer navigates with its own
   *  router (locale-aware for customers, next/navigation for operator pages). */
  onRedirect: () => void;
}

export default function LogoutConfirmDialog({ onClose, onRedirect }: Props) {
  const t = useTranslations("Shared");
  const { dbUser, logout } = useAuth();
  const [phase, setPhase] = useState<"confirm" | "farewell">("confirm");
  const [pending, setPending] = useState(false);

  // Capture the role once at mount — before logout() nulls dbUser — so the
  // farewell copy stays correct. The dialog only mounts while signed in.
  const [role] = useState(dbUser?.role ?? null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clear the redirect timer if we unmount early (e.g. user navigates away)
  // so we never call onRedirect / setState after unmount.
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const handleConfirm = () => {
    if (pending) return;
    setPending(true);
    // Do NOT log out yet. logout() synchronously nulls auth state, and several
    // consumers stop rendering this dialog the instant that happens — the
    // account layout guard early-returns + redirects, the operator navbar
    // variant is role-derived, the seller pending page polls on `token`. Any
    // of those unmounts the farewell (or redirects) before it can show. So we
    // keep auth stable for the hold, then navigate + log out together at the
    // end. The closure captures this click's onRedirect; the timer fires once.
    setPhase("farewell");
    timerRef.current = setTimeout(() => {
      onRedirect();
      logout();
      // Explicitly dismiss — do NOT rely on the navigation to unmount us. When
      // the redirect target is the current route (e.g. a customer logging out
      // from "/"), router.push is a no-op and the dialog would otherwise stay
      // mounted, leaving the farewell overlay stuck on screen.
      onClose();
    }, FAREWELL_HOLD_MS);
  };

  const handleClose = () => {
    if (!pending) onClose();
  };

  if (phase === "confirm") {
    return (
      <Modal
        title={t("logout.confirmTitle")}
        size="sheet"
        onClose={handleClose}
        footer={
          <>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={pending}
              onClick={handleClose}
            >
              {t("logout.cancel")}
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={pending}
              onClick={handleConfirm}
              autoFocus
            >
              {t("logout.confirmCta")}
            </button>
          </>
        }
      >
        <p className={styles.confirmBody}>{t("logout.confirmBody")}</p>
      </Modal>
    );
  }

  // Farewell phase.
  const message =
    role === "customer"
      ? t("logout.farewellCustomer")
      : t("logout.farewellStaff");

  return createPortal(
    <div className={styles.farewellBackdrop} role="status" aria-live="polite">
      <div className={styles.farewellCard}>
        <span className={styles.checkCircle} aria-hidden>
          ✓
        </span>
        <p className={styles.farewellText}>{message}</p>
      </div>
    </div>,
    document.body,
  );
}
