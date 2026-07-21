"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { use, useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AdminReasonModal from "@/components/admin/AdminReasonModal";
import CustomerStatusPill from "@/components/admin/CustomerStatusPill";
import { useAuth } from "@/lib/AuthContext";
import { customerLifecycleAction, fetchCustomerHub } from "@/lib/adminCustomers";
import type {
  AdminCustomerHub,
  CustomerAccountStatus,
  CustomerLifecycleAction,
} from "@/types";
import styles from "./layout.module.css";

const TABS: { slug: string; labelKey: string }[] = [
  { slug: "", labelKey: "tab.overview" },
  { slug: "activity", labelKey: "tab.activity" },
  { slug: "orders", labelKey: "tab.orders" },
  { slug: "addresses", labelKey: "tab.addresses" },
  { slug: "notifications", labelKey: "tab.notifications" },
];

// Which lifecycle actions apply to each state.
const ACTIONS_BY_STATUS: Record<
  CustomerAccountStatus,
  CustomerLifecycleAction[]
> = {
  active: ["suspend", "delete"],
  deactivated: ["suspend", "delete"],
  suspended: ["unsuspend", "delete"],
  deleted: ["restore"],
};

// Destructive actions get the red confirm button in the reason modal.
const DESTRUCTIVE = new Set<CustomerLifecycleAction>(["suspend", "delete"]);

function initialsFor(hub: AdminCustomerHub): string {
  const source = hub.full_name?.trim() || hub.email;
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return source.slice(0, 2).toUpperCase();
}

export default function CustomerHubLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const t = useTranslations("Admin.customers");
  const tc = useTranslations("Admin.common");
  const router = useRouter();
  const pathname = usePathname();
  const { token, dbUser, loading } = useAuth();
  const [hub, setHub] = useState<AdminCustomerHub | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [pending, setPending] = useState<CustomerLifecycleAction | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (loading || !dbUser || dbUser.role !== "admin" || !token) return;
    try {
      const data = await fetchCustomerHub(Number(id), token);
      setHub(data);
      setErr(null);
    } catch {
      setErr(t("loadError"));
    }
  }, [id, token, dbUser, loading, t]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial load sets state inside async callbacks
    load();
  }, [load]);

  async function performAction(reason: string) {
    if (!pending || !token) return;
    setActionError(null);
    try {
      await customerLifecycleAction(Number(id), pending, reason, token);
      setPending(null);
      await load();
    } catch (e) {
      const detail = (e as { detail?: unknown }).detail;
      const code =
        detail && typeof detail === "object" && "error" in detail
          ? String((detail as { error: unknown }).error)
          : undefined;
      setActionError(
        code === "invalid_transition"
          ? t("actions.invalidTransition")
          : t("actions.failed"),
      );
      setPending(null);
    }
  }

  // Active tab = the path segment immediately after the customer id (empty ->
  // overview).
  const segments = pathname.split("/").filter(Boolean);
  const idIdx = segments.indexOf(id);
  const activeSlug =
    idIdx >= 0 && segments.length > idIdx + 1 ? segments[idIdx + 1] : "";

  if (err) {
    return (
      <div className={styles.error}>
        {err} —{" "}
        <button onClick={() => router.push("/admin/customers")}>
          {tc("back")}
        </button>
      </div>
    );
  }
  if (!hub) {
    return <div className={styles.loading}>{tc("loading")}</div>;
  }

  const actions = ACTIONS_BY_STATUS[hub.account_status] ?? [];

  return (
    <div className={styles.wrap}>
      <nav className={styles.breadcrumb} aria-label="Breadcrumb">
        <Link href="/admin/customers">{t("breadcrumbRoot")}</Link>
        <span aria-hidden>›</span>
        <span className={styles.breadcrumbCurrent}>
          {hub.full_name || hub.email}
        </span>
      </nav>

      <div className={styles.banner} role="status" aria-live="polite">
        <span aria-hidden>👤</span>
        <span>{t("viewingBanner")}</span>
      </div>

      <div className={styles.headerCard}>
        <div className={styles.avatar} aria-hidden>
          {initialsFor(hub)}
        </div>
        <div className={styles.identity}>
          <div className={styles.nameRow}>
            <h2 className={styles.name}>{hub.full_name || t("noName")}</h2>
            <CustomerStatusPill status={hub.account_status} />
          </div>
          <div className={styles.contact}>{hub.email}</div>
          {hub.phone && <div className={styles.contact}>{hub.phone}</div>}
        </div>
        <div className={styles.stats}>
          <div className={styles.stat}>
            <span className={styles.statValue}>{hub.open_orders}</span>
            <span className={styles.statLabel}>{t("stat.openOrders")}</span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statValue}>{hub.open_credit_accounts}</span>
            <span className={styles.statLabel}>{t("stat.openCredit")}</span>
          </div>
        </div>
      </div>

      {actionError && (
        <div className={styles.actionError} role="alert">
          {actionError}
        </div>
      )}

      {actions.length > 0 && (
        <div className={styles.actions}>
          {actions.map((action) => (
            <button
              key={action}
              type="button"
              className={
                action === "delete"
                  ? "btn btn-danger"
                  : action === "suspend"
                    ? "btn btn-outline"
                    : "btn btn-primary"
              }
              onClick={() => {
                setActionError(null);
                setPending(action);
              }}
            >
              {t(`actions.${action}`)}
            </button>
          ))}
        </div>
      )}

      <div className={styles.tabs}>
        {TABS.map((tab) => {
          const href = tab.slug
            ? `/admin/customers/${id}/${tab.slug}`
            : `/admin/customers/${id}`;
          const active = activeSlug === tab.slug;
          return (
            <Link
              key={tab.slug || "overview"}
              href={href}
              className={active ? styles.tabActive : styles.tab}
            >
              {t(tab.labelKey)}
            </Link>
          );
        })}
      </div>

      <div className={styles.content}>{children}</div>

      {pending && (
        <AdminReasonModal
          title={t(`actions.modalTitle.${pending}`, {
            name: hub.full_name || hub.email,
          })}
          description={t(`actions.modalDesc.${pending}`)}
          confirmLabel={t(`actions.${pending}`)}
          destructive={DESTRUCTIVE.has(pending)}
          onConfirm={performAction}
          onClose={() => setPending(null)}
        />
      )}
    </div>
  );
}
