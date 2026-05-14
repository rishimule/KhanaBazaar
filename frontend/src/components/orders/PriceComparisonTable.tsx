// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

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
            <td className={styles.num}>{formatINR(sourceSubtotal)}</td>
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
                {formatINR(alt.effective_total)}
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">{t("footAction")}</th>
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
  );
}
