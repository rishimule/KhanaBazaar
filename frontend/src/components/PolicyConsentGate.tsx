"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState } from "react";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import Modal from "@/components/Modal";
import { useAuth } from "@/lib/AuthContext";

/** Blocking re-consent gate. Renders nothing unless the logged-in user needs to
 *  accept the current policy version. Mounted once per route group (inside each
 *  AuthProvider), so it covers both customer and operator areas. */
export default function PolicyConsentGate() {
  const t = useTranslations("PolicyConsent");
  const { dbUser, loading, acceptPolicies, logout } = useAuth();
  const pathname = usePathname();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (loading || !dbUser || !dbUser.needs_policy_acceptance) return null;
  // Don't block the very pages the modal links to — a re-consenting user must
  // be able to read the Terms/Privacy before accepting. (Matches /terms,
  // /privacy and their locale-prefixed variants e.g. /hi/terms.)
  if (pathname.endsWith("/terms") || pathname.endsWith("/privacy")) return null;

  const handleAccept = async () => {
    setError(null);
    setSubmitting(true);
    try {
      await acceptPolicies();
    } catch {
      setError(t("error"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={t("title")}
      onClose={() => {}}
      dismissible={false}
      footer={
        <>
          <button
            type="button"
            className="btn"
            onClick={logout}
            disabled={submitting}
          >
            {t("logout")}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleAccept}
            disabled={submitting}
          >
            {submitting ? t("accepting") : t("accept")}
          </button>
        </>
      }
    >
      {error && (
        <p role="alert" style={{ color: "var(--color-danger, #c0392b)" }}>
          {error}
        </p>
      )}
      <p>
        {t.rich("body", {
          terms: (chunks) => (
            <a href="/terms" target="_blank" rel="noopener noreferrer">
              {chunks}
            </a>
          ),
          privacy: (chunks) => (
            <a href="/privacy" target="_blank" rel="noopener noreferrer">
              {chunks}
            </a>
          ),
        })}
      </p>
    </Modal>
  );
}
