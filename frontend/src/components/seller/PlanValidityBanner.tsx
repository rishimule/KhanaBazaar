// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import LoadError from "@/components/LoadError";
import { useAuth } from "@/lib/AuthContext";
import { getMyPlan, type SellerPlanServiceView } from "@/lib/sellerPlan";
import { useResource } from "@/lib/useResource";
import styles from "./PlanValidityBanner.module.css";

type Tone = "danger" | "warn" | "info" | "success";

function daysLeft(iso: string): number {
  return Math.ceil(
    (new Date(`${iso.slice(0, 10)}T00:00:00`).getTime() - Date.now()) / 86_400_000,
  );
}

type Translator = (key: string, values?: Record<string, string | number>) => string;

// Pick the single most-urgent plan message across the store's services.
// `summarize` runs outside the component (inside an effect), so the translator
// is passed in rather than pulled from the hook here.
function summarize(
  services: SellerPlanServiceView[],
  isPremium: boolean,
  t: Translator,
): { tone: Tone; text: string } | null {
  const suspended = services.find((s) => s.status === "suspended");
  if (suspended) {
    return { tone: "danger", text: t("bannerSuspended", { service: suspended.service_name }) };
  }
  const pending = services.find((s) => s.payment_pending);
  if (pending) {
    return { tone: "info", text: t("bannerPending", { service: pending.service_name }) };
  }
  const grace = services.find((s) => s.status === "grace");
  if (grace) {
    return { tone: "warn", text: t("bannerGrace", { service: grace.service_name }) };
  }
  let soon: { name: string; d: number } | null = null;
  for (const s of services) {
    if (s.model === "freebie" && s.subscription_enabled && s.valid_until) {
      const d = daysLeft(s.valid_until);
      if (Number.isFinite(d) && d <= 14 && (!soon || d < soon.d)) soon = { name: s.service_name, d };
    }
  }
  if (soon) {
    return {
      tone: "warn",
      text:
        soon.d > 0
          ? t("bannerTrialEndsIn", { service: soon.name, days: soon.d })
          : t("bannerTrialEnded", { service: soon.name }),
    };
  }
  if (isPremium) {
    return { tone: "success", text: t("bannerPremium") };
  }
  return null;
}

export default function PlanValidityBanner({ isPremium }: { isPremium: boolean }) {
  const { token } = useAuth();
  const t = useTranslations("Plan");
  // Swallowing this used to return `null`, so a seller whose service was
  // suspended for non-payment could be shown no warning at all. `null` is now
  // reserved for "genuinely nothing to say".
  const { data: plan, error, refetch } = useResource(
    token ? () => getMyPlan(token) : null,
    [Boolean(token)],
  );

  const summary = plan ? summarize(plan.services, isPremium, t) : null;

  if (error && !summary) {
    return (
      <LoadError
        variant="banner"
        error={error}
        title={t("bannerLoadFailed")}
        onRetry={() => refetch()}
      />
    );
  }

  if (!summary) return null;
  return (
    <div className={`${styles.banner} ${styles[summary.tone]}`} role="status">
      <span className={styles.text}>{summary.text}</span>
      <Link href="/seller/plan" className={styles.link}>
        {t("bannerManage")}
      </Link>
    </div>
  );
}
