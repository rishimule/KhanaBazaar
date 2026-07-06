// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAuth } from "@/lib/AuthContext";
import { getMyPlan, type SellerPlanServiceView } from "@/lib/sellerPlan";
import styles from "./PlanValidityBanner.module.css";

type Tone = "danger" | "warn" | "info" | "success";

function daysLeft(iso: string): number {
  return Math.ceil(
    (new Date(`${iso.slice(0, 10)}T00:00:00`).getTime() - Date.now()) / 86_400_000,
  );
}

// Pick the single most-urgent plan message across the store's services.
function summarize(
  services: SellerPlanServiceView[],
  isPremium: boolean,
): { tone: Tone; text: string } | null {
  const suspended = services.find((s) => s.status === "suspended");
  if (suspended) {
    return { tone: "danger", text: `${suspended.service_name} is suspended — renew to restore it.` };
  }
  const pending = services.find((s) => s.payment_pending);
  if (pending) {
    return { tone: "info", text: `Payment under review for ${pending.service_name}.` };
  }
  const grace = services.find((s) => s.status === "grace");
  if (grace) {
    return {
      tone: "warn",
      text: `${grace.service_name} is in its grace period — renew now to avoid suspension.`,
    };
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
          ? `${soon.name} free trial ends in ${soon.d} day${soon.d === 1 ? "" : "s"} — upgrade to go premium.`
          : `${soon.name} free trial has ended.`,
    };
  }
  const cancelling = services.find((s) => s.cancel_requested);
  if (cancelling) {
    return { tone: "warn", text: `${cancelling.service_name} subscription is set to cancel at term end.` };
  }
  if (isPremium) {
    return { tone: "success", text: "Your store is premium — all paid plans are in good standing." };
  }
  return null;
}

export default function PlanValidityBanner({ isPremium }: { isPremium: boolean }) {
  const { token } = useAuth();
  const [summary, setSummary] = useState<{ tone: Tone; text: string } | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    getMyPlan(token)
      .then((v) => {
        if (!cancelled) setSummary(summarize(v.services, isPremium));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [token, isPremium]);

  if (!summary) return null;
  return (
    <div className={`${styles.banner} ${styles[summary.tone]}`} role="status">
      <span className={styles.text}>{summary.text}</span>
      <Link href="/seller/plan" className={styles.link}>
        Manage plan →
      </Link>
    </div>
  );
}
