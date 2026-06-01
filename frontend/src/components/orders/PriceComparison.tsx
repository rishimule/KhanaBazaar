// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { useCart } from "@/lib/CartContext";
import { apiErrorKey } from "@/lib/errors";
import { fetchCompare, replaceSubBasket } from "@/lib/priceComparison";
import type { Cart, ComparisonAlternative } from "@/types";
import PriceComparisonTable from "./PriceComparisonTable";
import SwitchStoreDialog from "./SwitchStoreDialog";
import styles from "./PriceComparison.module.css";

interface Props {
  sourceStoreId: number;
  sourceStoreName: string;
  serviceId: number;
  serviceName: string;
  customerAddressId: number | null;
  serviceable: boolean;
  pickerLoading: boolean;
  cart: Cart;
}

type Status =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "loaded"; alternatives: ComparisonAlternative[] }
  | { kind: "empty" }
  | { kind: "error"; messageKey: string };

function TagIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M20.59 13.41 13.42 20.6a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
      <circle cx="7" cy="7" r="1.2" fill="currentColor" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 2 4 5v6c0 5 3.4 8.6 8 11 4.6-2.4 8-6 8-11V5z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

function formatINR(value: number): string {
  return `₹${value.toFixed(2)}`;
}

export default function PriceComparison({
  sourceStoreId,
  sourceStoreName,
  serviceId,
  customerAddressId,
  serviceable,
  pickerLoading,
  cart,
}: Props) {
  const t = useTranslations("Checkout.compare");
  const tErr = useTranslations("Errors");
  const { token } = useAuth();
  const { carts, refresh, setReplaceAdjustments, clearReplaceAdjustments } = useCart();
  const router = useRouter();

  const [expanded, setExpanded] = useState(false);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [chosen, setChosen] = useState<ComparisonAlternative | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [dialogErrorKey, setDialogErrorKey] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const gateDisabled =
    pickerLoading || !serviceable || customerAddressId === null;

  const runFetch = useCallback(async () => {
    if (!token || customerAddressId === null) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setStatus({ kind: "loading" });
    try {
      const data = await fetchCompare(
        token,
        sourceStoreId,
        serviceId,
        customerAddressId,
        ctrl.signal,
      );
      if (ctrl.signal.aborted) return;
      if (data.alternatives.length === 0) {
        setStatus({ kind: "empty" });
      } else {
        setStatus({ kind: "loaded", alternatives: data.alternatives });
      }
    } catch (e) {
      if (ctrl.signal.aborted) return;
      const key = apiErrorKey(e) ?? "Errors.network";
      setStatus({ kind: "error", messageKey: key });
    }
  }, [token, customerAddressId, sourceStoreId, serviceId]);

  const onToggle = useCallback(() => {
    setExpanded((prev) => {
      const next = !prev;
      if (next) {
        void runFetch();
      } else {
        abortRef.current?.abort();
        setStatus({ kind: "idle" });
      }
      return next;
    });
  }, [runFetch]);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const onConfirmSwitch = useCallback(async () => {
    if (!token || !chosen) return;
    setSubmitting(true);
    setDialogErrorKey(null);
    try {
      const items = chosen.items
        .filter((i) => !i.imputed && i.inventory_id !== null)
        .map((i) => ({
          inventory_id: i.inventory_id as number,
          quantity: i.quantity,
        }));
      const res = await replaceSubBasket(token, chosen.id, serviceId, items);
      setReplaceAdjustments(res.adjustments);
      await refresh();
      const altId = chosen.id;
      setChosen(null);
      router.push(`/checkout/${altId}/${serviceId}`);
    } catch (e) {
      const key = apiErrorKey(e);
      if (key === "Errors.service_unavailable" || key === "Errors.service_mismatch") {
        clearReplaceAdjustments();
        setChosen(null);
        router.push("/cart");
        return;
      }
      setDialogErrorKey(key ?? "Errors.network");
    } finally {
      setSubmitting(false);
    }
  }, [token, chosen, serviceId, setReplaceAdjustments, clearReplaceAdjustments, refresh, router]);

  const preExistingCount = chosen
    ? (carts.find((c) => c.store_id === chosen.id && c.service_id === serviceId)?.items.length ?? 0)
    : 0;

  const errKey = status.kind === "error"
    ? (status.messageKey.startsWith("Errors.") ? status.messageKey.slice("Errors.".length) : status.messageKey)
    : null;

  return (
    <section className={styles.section}>
      <button
        type="button"
        className={styles.toggle}
        onClick={onToggle}
        disabled={gateDisabled}
        aria-expanded={expanded}
        aria-controls="price-comparison-panel"
      >
        <span className={styles.headIcon} aria-hidden><TagIcon /></span>
        <span className={styles.headText}>
          <span className={styles.headTitle}>{t("headerTitle")}</span>
          {status.kind === "loaded" && (
            <span className={styles.headSub}>
              {t("headerSubhead", { count: status.alternatives.length })}
            </span>
          )}
        </span>
        <span className={styles.chev}>{expanded ? "▴" : "▾"}</span>
      </button>
      {gateDisabled && (
        <p className={styles.hint}>{t("toggleDisabledHint")}</p>
      )}
      {expanded && (
        <div id="price-comparison-panel" className={styles.panel}>
          {status.kind === "loading" && (
            <p className={styles.muted}>{t("loading")}</p>
          )}
          {status.kind === "empty" && (
            <p className={styles.muted}>{t("emptyState")}</p>
          )}
          {status.kind === "error" && errKey && (
            <div className={styles.errorBlock}>
              <p>{tErr(errKey)}</p>
              <button
                type="button"
                className={styles.retryBtn}
                onClick={() => void runFetch()}
              >
                {t("retry")}
              </button>
            </div>
          )}
          {status.kind === "loaded" && (
            <>
              <CompareBanner
                sourceStoreName={sourceStoreName}
                sourceSubtotal={cart.items.reduce(
                  (acc, i) => acc + i.price * i.quantity,
                  0,
                )}
                alternatives={status.alternatives}
              />
              <PriceComparisonTable
                sourceCart={cart}
                alternatives={status.alternatives}
                shopDisabled={chosen !== null || submitting}
                onShopAt={(alt) => {
                  setChosen(alt);
                  setDialogErrorKey(null);
                }}
              />
              <p className={styles.footerNote}>
                <ClockIcon /> {t("footerNote")}
              </p>
            </>
          )}
        </div>
      )}
      {chosen && (
        <SwitchStoreDialog
          alternative={chosen}
          sourceStoreName={sourceStoreName}
          preExistingItemCount={preExistingCount}
          submitting={submitting}
          errorKey={dialogErrorKey}
          onConfirm={onConfirmSwitch}
          onCancel={() => {
            if (submitting) return;
            setChosen(null);
            setDialogErrorKey(null);
          }}
        />
      )}
    </section>
  );
}

interface BannerProps {
  sourceStoreName: string;
  sourceSubtotal: number;
  alternatives: ComparisonAlternative[];
}

function CompareBanner({ sourceStoreName, sourceSubtotal, alternatives }: BannerProps) {
  const t = useTranslations("Checkout.compare");
  const cheapestAlt = alternatives.reduce<ComparisonAlternative | null>(
    (best, a) =>
      best === null || a.effective_total < best.effective_total ? a : best,
    null,
  );
  const sourceIsBest =
    cheapestAlt === null || sourceSubtotal <= cheapestAlt.effective_total;

  if (sourceIsBest) {
    return (
      <div className={`${styles.banner} ${styles.bannerGood}`} role="status">
        <span className={styles.bannerIcon} aria-hidden><ShieldIcon /></span>
        <span>{t("bannerBest", { store: sourceStoreName })}</span>
      </div>
    );
  }

  const saved = sourceSubtotal - cheapestAlt.effective_total;
  return (
    <div className={`${styles.banner} ${styles.bannerSave}`} role="status">
      <span className={styles.bannerIcon} aria-hidden><ShieldIcon /></span>
      <span>
        {t("bannerSave", { amount: formatINR(saved), store: cheapestAlt.name })}
      </span>
    </div>
  );
}
