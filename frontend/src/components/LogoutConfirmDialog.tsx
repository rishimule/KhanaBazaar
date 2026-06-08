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

  // Capture the role before logout() nulls dbUser, so the farewell copy is
  // correct. The dialog only mounts while signed in, so mount value is good.
  const roleRef = useRef(dbUser?.role ?? null);
  // Hold the latest onRedirect so the timer never fires a stale closure.
  const onRedirectRef = useRef(onRedirect);
  onRedirectRef.current = onRedirect;
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
    logout(); // synchronous; push teardown is its own fire-and-forget inside
    setPhase("farewell");
    timerRef.current = setTimeout(() => {
      onRedirectRef.current();
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
    roleRef.current === "customer"
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
