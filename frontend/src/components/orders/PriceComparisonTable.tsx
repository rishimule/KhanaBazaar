// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import type { Cart, ComparisonAlternative, ComparisonItem } from "@/types";
import styles from "./PriceComparisonTable.module.css";

interface Props {
  sourceCart: Cart;
  alternatives: ComparisonAlternative[];
  onShopAt: (alt: ComparisonAlternative) => void;
  shopDisabled?: boolean;
}

const CATEGORY_EMOJI: Record<number, string> = {
  1: "🥬",
  2: "🥛",
  3: "🌾",
  4: "🍪",
};

function formatINR(value: number): string {
  return `₹${value.toFixed(2)}`;
}

function StoreGlyph() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M3 9l1.5-5h15L21 9M4 9v10a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V9M3 9h18M9 20v-6h6v6" />
    </svg>
  );
}

function TruckGlyph() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M1 3h15v13H1zM16 8h4l3 3v5h-7zM5.5 19a1.5 1.5 0 1 0 0 .01M18.5 19a1.5 1.5 0 1 0 0 .01" />
    </svg>
  );
}

function CompareItemImage({ item }: { item: ComparisonItem }) {
  const [imgFailed, setImgFailed] = useState(false);
  const showImage = Boolean(item.image_url) && !imgFailed;
  const glyph = CATEGORY_EMOJI[item.category_id] ?? "📦";
  return (
    <span className={styles.itemThumb} aria-hidden>
      {showImage ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={item.image_url as string}
          alt=""
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setImgFailed(true)}
        />
      ) : (
        <span className={styles.thumbGlyph}>{glyph}</span>
      )}
    </span>
  );
}

function lineTotalLabel(unitPrice: number, quantity: number): string {
  const total = formatINR(unitPrice * quantity);
  return quantity > 1 ? `${total} (×${quantity})` : total;
}

export default function PriceComparisonTable({
  sourceCart,
  alternatives,
  onShopAt,
  shopDisabled = false,
}: Props) {
  const t = useTranslations("Checkout.compare");
  const sourceSubtotal = sourceCart.items.reduce(
    (acc, i) => acc + i.price * i.quantity,
    0,
  );

  return (
    <div className={styles.grid}>
      {/* Source store card */}
      <article
        className={`${styles.card} ${styles.sourceCard}`}
        aria-labelledby="cmp-source-name"
      >
        <span className={styles.yourCartPill}>{t("yourCartPill")}</span>
        <header className={styles.cardHead}>
          <span className={styles.avatar} aria-hidden><StoreGlyph /></span>
          <div className={styles.headText}>
            <span id="cmp-source-name" className={styles.cardName}>
              {sourceCart.store_name}
            </span>
            <span className={styles.cardSub}>{t("yourStoreItemTag")}</span>
          </div>
        </header>

        <div className={styles.priceBig}>{formatINR(sourceSubtotal)}</div>
        <span className={styles.currentChip}>{t("currentStoreChip")}</span>
        <span className={`${styles.deliveryPill} ${styles.deliveryGood}`}>
          <TruckGlyph /> {t("shipsOneDelivery")}
        </span>

        <ul className={styles.itemList}>
          {sourceCart.items.map((src) => (
            <li key={src.product_id} className={styles.itemRow}>
              <CompareItemImage
                item={{
                  product_id: src.product_id,
                  product_name: src.product_name,
                  quantity: src.quantity,
                  inventory_id: src.inventory_id,
                  unit_price: src.price,
                  is_available: true,
                  stock: 0,
                  line_total: src.price * src.quantity,
                  imputed: false,
                  image_url: src.image_url ?? null,
                  category_id: 0,
                }}
              />
              <div className={styles.itemMain}>
                <span className={styles.itemName}>{src.product_name}</span>
              </div>
              <span className={styles.itemPrice}>
                {lineTotalLabel(src.price, src.quantity)}
              </span>
            </li>
          ))}
        </ul>

        <button
          type="button"
          className={styles.selectedBtn}
          disabled
          aria-disabled
        >
          ✓ {t("selectedBtn")}
        </button>
      </article>

      {/* Alternative cards */}
      {alternatives.map((alt) => {
        const headerId = `cmp-alt-${alt.id}-name`;
        const oneDelivery = alt.missing_count === 0;
        return (
          <article
            key={alt.id}
            className={styles.card}
            aria-labelledby={headerId}
          >
            <header className={styles.cardHead}>
              <span className={styles.avatar} aria-hidden><StoreGlyph /></span>
              <div className={styles.headText}>
                <span id={headerId} className={styles.cardName}>{alt.name}</span>
                <span className={styles.cardSub}>
                  {t("kmAway", { km: alt.distance_km.toFixed(1) })}
                </span>
              </div>
            </header>

            <div className={styles.priceBig}>{formatINR(alt.effective_total)}</div>
            <DeltaChip
              effectiveTotal={alt.effective_total}
              sourceSubtotal={sourceSubtotal}
            />
            <span
              className={`${styles.deliveryPill} ${oneDelivery ? styles.deliveryGood : styles.deliveryWarn}`}
            >
              <TruckGlyph />{" "}
              {oneDelivery ? t("shipsOneDelivery") : t("arrivesTwoDeliveries")}
            </span>

            <ul className={styles.itemList}>
              {sourceCart.items.map((src) => {
                const item = alt.items.find((i) => i.product_id === src.product_id);
                const imputed = !item || item.imputed;
                const unit = item ? item.unit_price : src.price;
                const qty = item ? item.quantity : src.quantity;
                const cat = item ? item.category_id : 0;
                const img = item ? item.image_url : (src.image_url ?? null);
                return (
                  <li key={src.product_id} className={styles.itemRow}>
                    <CompareItemImage
                      item={{
                        product_id: src.product_id,
                        product_name: src.product_name,
                        quantity: qty,
                        inventory_id: null,
                        unit_price: unit,
                        is_available: !imputed,
                        stock: 0,
                        line_total: unit * qty,
                        imputed,
                        image_url: img,
                        category_id: cat,
                      }}
                    />
                    <div className={styles.itemMain}>
                      <span className={styles.itemName}>{src.product_name}</span>
                      {imputed && (
                        <span className={styles.yourStoreTag}>
                          {t("yourStoreItemTag")}
                        </span>
                      )}
                    </div>
                    <span className={styles.itemPrice}>
                      {lineTotalLabel(unit, qty)}
                    </span>
                  </li>
                );
              })}
            </ul>

            {(alt.covered_count > 0 || alt.missing_count > 0) && (
              <div className={styles.summary}>
                {alt.covered_count > 0 && (
                  <div className={styles.summaryRow}>
                    <span>
                      {t("summaryFromThisStore", { count: alt.covered_count })}
                    </span>
                    <span className={styles.summaryAmt}>
                      {formatINR(alt.covered_subtotal)}
                    </span>
                  </div>
                )}
                {alt.missing_count > 0 && (
                  <div className={styles.summaryRow}>
                    <span>
                      {t("summaryFromSource", {
                        count: alt.missing_count,
                        store: sourceCart.store_name,
                      })}
                    </span>
                    <span className={styles.summaryAmt}>
                      {formatINR(alt.imputed_subtotal)}
                    </span>
                  </div>
                )}
              </div>
            )}

            <button
              type="button"
              className={styles.switchBtn}
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
    diff < 0 ? styles.deltaSave : diff > 0 ? styles.deltaMore : styles.deltaSame;
  const chipText =
    diff < 0
      ? t("saveDelta", { amount: formatINR(absDiff) })
      : diff > 0
      ? `+${t("moreDelta", { amount: formatINR(absDiff) })}`
      : t("sameTotal");
  return <span className={`${styles.deltaChip} ${chipClass}`}>{chipText}</span>;
}
