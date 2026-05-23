// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import type { Cart, ComparisonAlternative } from "@/types";
import styles from "./PriceComparisonTable.module.css";

interface Props {
  sourceCart: Cart;
  alternatives: ComparisonAlternative[];
  onShopAt: (alt: ComparisonAlternative) => void;
  shopDisabled?: boolean;
}

function formatINR(value: number): string {
  return `₹${value.toFixed(2)}`;
}

export default function PriceComparisonTable({
  sourceCart,
  alternatives,
  onShopAt,
  shopDisabled = false,
}: Props) {
  const t = useTranslations("Checkout.compare");
  const sourceItemByProductId = new Map(
    sourceCart.items.map((i) => [i.product_id, i]),
  );
  const productIds = sourceCart.items.map((i) => i.product_id);
  const sourceSubtotal = sourceCart.items.reduce(
    (acc, i) => acc + i.price * i.quantity,
    0,
  );
  const totalCartItems = sourceCart.items.length;

  return (
    <div className={styles.wrap}>
      {/* Desktop table (≥ 769px) */}
      <div className={styles.desktopTable}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col" className={styles.itemCol}>
                {t("colItem")}
              </th>
              <th scope="col">
                {sourceCart.store_name}
                <div className={styles.subhead}>{t("currentSubhead")}</div>
              </th>
              {alternatives.map((alt) => (
                <th key={alt.id} scope="col">
                  {alt.name}
                  <div className={styles.subhead}>
                    {t("kmAway", { km: alt.distance_km.toFixed(1) })}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {productIds.map((pid) => {
              const src = sourceItemByProductId.get(pid)!;
              return (
                <tr key={pid}>
                  <th scope="row" className={styles.itemName}>
                    {src.product_name}
                  </th>
                  <td className={styles.num}>
                    {formatINR(src.price)} × {src.quantity}
                  </td>
                  {alternatives.map((alt) => {
                    const item = alt.items.find((i) => i.product_id === pid);
                    if (!item || item.imputed) {
                      return (
                        <td key={alt.id} className={styles.missing}>
                          {t("notStocked")}
                        </td>
                      );
                    }
                    return (
                      <td key={alt.id} className={styles.num}>
                        {formatINR(item.unit_price)} × {item.quantity}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">{t("footAtStore")}</th>
              <td className={styles.num}>—</td>
              {alternatives.map((alt) => (
                <td key={alt.id} className={styles.num}>
                  {formatINR(alt.covered_subtotal)}{" "}
                  <span className={styles.coverage}>
                    ({alt.covered_count}/{totalCartItems})
                  </span>
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row">{t("footStaysAtA", { store: sourceCart.store_name })}</th>
              <td>—</td>
              {alternatives.map((alt) => (
                <td key={alt.id} className={styles.num}>
                  {alt.imputed_subtotal > 0
                    ? `${formatINR(alt.imputed_subtotal)} (${alt.missing_count})`
                    : "—"}
                </td>
              ))}
            </tr>
            <tr className={styles.combinedRow}>
              <th scope="row">{t("footCombined")}</th>
              <td className={styles.num}>{formatINR(sourceSubtotal)}</td>
              {alternatives.map((alt) => (
                <td key={alt.id} className={styles.num}>
                  {formatINR(alt.effective_total)}{" "}
                  <DeltaChip
                    effectiveTotal={alt.effective_total}
                    sourceSubtotal={sourceSubtotal}
                  />
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row"><span className="sr-only">{t("footAction")}</span></th>
              <td className={styles.currentLabel}>{t("currentBadge")}</td>
              {alternatives.map((alt) => (
                <td key={alt.id}>
                  <button
                    type="button"
                    className={styles.shopBtn}
                    onClick={() => onShopAt(alt)}
                    disabled={shopDisabled}
                  >
                    {t("shopAt", { store: alt.name })}
                  </button>
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>

      {/* Mobile stack (≤ 768px) */}
      <MobileComparison
        sourceCart={sourceCart}
        sourceSubtotal={sourceSubtotal}
        totalCartItems={totalCartItems}
        alternatives={alternatives}
        onShopAt={onShopAt}
        shopDisabled={shopDisabled}
      />
    </div>
  );
}

interface MobileProps {
  sourceCart: Cart;
  sourceSubtotal: number;
  totalCartItems: number;
  alternatives: ComparisonAlternative[];
  onShopAt: (alt: ComparisonAlternative) => void;
  shopDisabled: boolean;
}

function MobileComparison({
  sourceCart,
  sourceSubtotal,
  totalCartItems,
  alternatives,
  onShopAt,
  shopDisabled,
}: MobileProps) {
  const t = useTranslations("Checkout.compare");
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  function toggle(id: number): void {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  const sourceHeaderId = "source-store-name";

  return (
    <div className={styles.mobileStack}>
      {/* Source card */}
      <section className={styles.sourceCard} aria-labelledby={sourceHeaderId}>
        <span className={styles.currentBadge}>{t("currentStoreBadge")}</span>
        <div id={sourceHeaderId} className={styles.cardName}>
          {sourceCart.store_name}
        </div>
        <div className={styles.cardSubMeta}>
          {t("subtotalLabel", { amount: formatINR(sourceSubtotal) })}
          {" · "}
          {t("itemCountLabel", { count: totalCartItems })}
        </div>
      </section>

      {/* Alt cards */}
      {alternatives.map((alt) => {
        const expanded = expandedIds.has(alt.id);
        const headerId = `alt-${alt.id}-name`;
        const panelId = `alt-items-${alt.id}`;

        return (
          <article
            key={alt.id}
            className={styles.altCard}
            aria-labelledby={headerId}
          >
            <div className={styles.cardHeader}>
              <span id={headerId} className={styles.cardName}>
                {alt.name}
              </span>
              <span className={styles.cardDistance}>
                ({t("kmAway", { km: alt.distance_km.toFixed(1) })})
              </span>
            </div>

            <div className={styles.cardTotal}>
              <span className={styles.cardAmount}>
                {formatINR(alt.effective_total)}
              </span>
              <DeltaChip
                effectiveTotal={alt.effective_total}
                sourceSubtotal={sourceSubtotal}
              />
            </div>

            <div className={styles.coverageLine}>
              {t("stocksXofY", {
                covered: alt.covered_count,
                total: totalCartItems,
              })}
            </div>

            {alt.missing_count > 0 && (
              <div className={styles.missingNote}>
                {t("onlyAtCurrent", { count: alt.missing_count })}
              </div>
            )}

            <button
              type="button"
              className={styles.expandToggle}
              onClick={() => toggle(alt.id)}
              aria-expanded={expanded}
              aria-controls={panelId}
            >
              <span>
                {expanded ? t("hideItemPrices") : t("viewItemPrices")}
              </span>
              <span className={styles.chev} aria-hidden="true">
                {expanded ? "▴" : "▾"}
              </span>
            </button>

            <div id={panelId} className={styles.itemList} hidden={!expanded}>
              {sourceCart.items.map((src) => {
                const item = alt.items.find(
                  (i) => i.product_id === src.product_id,
                );
                const missing = !item || item.imputed;
                return (
                  <div key={src.product_id} className={styles.itemRow}>
                    <span className={styles.mobileItemName}>
                      {src.product_name}
                    </span>
                    {missing ? (
                      <span className={styles.itemMissing}>
                        {t("onlyAtSourceLabel", {
                          store: sourceCart.store_name,
                        })}
                      </span>
                    ) : (
                      <span className={styles.itemPrice}>
                        {formatINR(item.unit_price)} × {item.quantity}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>

            <button
              type="button"
              className={styles.shopBtnMobile}
              onClick={() => onShopAt(alt)}
              disabled={shopDisabled}
            >
              {t("shopAt", { store: alt.name })}
            </button>
          </article>
        );
      })}
    </div>
  );
}

interface DeltaChipProps {
  effectiveTotal: number;
  sourceSubtotal: number;
}

function DeltaChip({ effectiveTotal, sourceSubtotal }: DeltaChipProps) {
  const t = useTranslations("Checkout.compare");
  const diff = effectiveTotal - sourceSubtotal;
  const absDiff = Math.abs(diff);
  const chipClass =
    diff < 0
      ? styles.deltaSave
      : diff > 0
      ? styles.deltaMore
      : styles.deltaSame;
  const chipText =
    diff < 0
      ? t("saveDelta", { amount: formatINR(absDiff) })
      : diff > 0
      ? t("moreDelta", { amount: formatINR(absDiff) })
      : t("sameTotal");
  return (
    <span className={`${styles.deltaChip} ${chipClass}`}>{chipText}</span>
  );
}
