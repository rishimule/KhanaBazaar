"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import styles from "./policies.module.css";

interface PolicyItem {
  kind: string;
  version: number;
  body: string;
  published_at: string | null;
}

export default function AdminPoliciesPage() {
  const t = useTranslations("Admin.policies");
  const { token } = useAuth();
  const [items, setItems] = useState<PolicyItem[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    get<PolicyItem[]>("/api/v1/admin/policies", token)
      .then((rows) => {
        setItems(rows);
        setDrafts(Object.fromEntries(rows.map((r) => [r.kind, r.body])));
      })
      .catch(() => setError(t("loadError")));
  };

  useEffect(() => {
    if (token) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const publish = async (kind: string) => {
    if (!window.confirm(t("confirmPublish"))) return;
    setBusy(kind);
    setError(null);
    setToast(null);
    try {
      const doc = await post<{ version: number }>(
        `/api/v1/admin/policies/${kind}`,
        { body: drafts[kind] ?? "" },
        token
      );
      setToast(t("published", { version: doc.version }));
      load();
    } catch {
      setError(t("publishError"));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className={styles.page}>
      <h2 className={styles.heading}>{t("heading")}</h2>
      <p className={styles.intro}>{t("intro")}</p>
      {error && (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      )}
      {toast && <p className={styles.toast}>{toast}</p>}
      {items.map((item) => (
        <section key={item.kind} className={styles.card}>
          <div className={styles.cardHeader}>
            <h3>{t(item.kind === "terms" ? "terms" : "privacy")}</h3>
            <span className={styles.version}>
              {item.version > 0
                ? t("currentVersion", { version: item.version })
                : t("notPublished")}
            </span>
          </div>
          <label className={styles.label} htmlFor={`body-${item.kind}`}>
            {t("bodyLabel")}
          </label>
          <textarea
            id={`body-${item.kind}`}
            className={styles.textarea}
            value={drafts[item.kind] ?? ""}
            onChange={(e) =>
              setDrafts((d) => ({ ...d, [item.kind]: e.target.value }))
            }
            rows={18}
          />
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => publish(item.kind)}
            disabled={busy === item.kind || !(drafts[item.kind] ?? "").trim()}
          >
            {busy === item.kind ? t("publishing") : t("publish")}
          </button>
        </section>
      ))}
    </div>
  );
}
