"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCart } from "@/lib/CartContext";
import type { CompareOffer, CompareResponse } from "@/lib/searchClient";
import styles from "./ProductOfferList.module.css";

type Props = {
  data: CompareResponse;
};

export function ProductOfferList({ data }: Props) {
  const t = useTranslations("Search");
  const { carts, addItem, removeItem, updateQty } = useCart();
  const { product, offers } = data;
  const [showUnavailable, setShowUnavailable] = useState(false);

  // Split offers: serviceable (in delivery radius) vs not. Within each group,
  // backend already sorted by price asc.
  const serviceable = offers.filter((o) => o.is_serviceable);
  const unavailable = offers.filter((o) => !o.is_serviceable);

  function qtyFor(storeId: number, serviceId: number): number {
    const cart = carts.find(
      (c) => c.store_id === storeId && c.service_id === serviceId,
    );
    return cart?.items.find((i) => i.product_id === product.id)?.quantity ?? 0;
  }

  async function handleAdd(offer: CompareOffer) {
    // Allow adding from non-deliverable stores too — deliverability is
    // re-validated at checkout. Still block genuinely unavailable/out-of-stock.
    if (!offer.is_available || offer.stock <= 0) return;
    await addItem(
      offer.store.id,
      offer.store.name,
      product.service_id,
      product.service_name ?? "",
      {
        product_id: product.id,
        inventory_id: offer.inventory_id,
        product_name: product.name,
        quantity: 1,
        price: offer.price,
        image_url: product.image_url ?? undefined,
      },
    );
  }

  function renderRow(o: CompareOffer) {
    const qty = qtyFor(o.store.id, product.service_id);
    const disabled = !o.is_available || o.stock <= 0;
    return (
      <li key={o.store.id} className={styles.row}>
        <div className={styles.storeMeta}>
          <Link href={`/stores/${o.store.id}`} className={styles.storeName}>
            {o.store.name}
          </Link>
          <div className={styles.subtext}>
            {o.store.distance_km !== null && (
              <span>{o.store.distance_km} km</span>
            )}
            {o.store.distance_km !== null &&
              (!o.is_serviceable || (o.is_serviceable && !o.is_available)) && (
                <span> · </span>
              )}
            {!o.is_serviceable && (
              <span className={styles.warning}>{t("notDeliverable")}</span>
            )}
            {o.is_serviceable && !o.is_available && (
              <span className={styles.warning}>{t("outOfStock")}</span>
            )}
          </div>
        </div>
        <div className={styles.price}>₹{o.price.toFixed(0)}</div>
        {qty === 0 ? (
          <button
            type="button"
            className={styles.addBtn}
            disabled={disabled}
            onClick={() => handleAdd(o)}
            aria-label={t("add")}
          >
            {t("add")}
          </button>
        ) : (
          <div
            className={styles.qtyControls}
            role="group"
            aria-label="Quantity"
          >
            <button
              type="button"
              className={styles.qtyBtn}
              onClick={() =>
                qty <= 1
                  ? removeItem(o.store.id, product.service_id, product.id)
                  : updateQty(o.store.id, product.service_id, product.id, qty - 1)
              }
              aria-label="Decrease quantity"
            >
              −
            </button>
            <span className={styles.qtyValue}>{qty}</span>
            <button
              type="button"
              className={styles.qtyBtn}
              onClick={() =>
                updateQty(o.store.id, product.service_id, product.id, qty + 1)
              }
              disabled={qty >= o.stock}
              aria-label="Increase quantity"
            >
              +
            </button>
          </div>
        )}
      </li>
    );
  }

  return (
    <div>
      {serviceable.length > 0 && (
        <ul className={styles.list}>{serviceable.map(renderRow)}</ul>
      )}
      {serviceable.length === 0 && (
        <div className={styles.emptyServiceable}>
          {t("notDeliverable")}.
        </div>
      )}
      {unavailable.length > 0 && (
        <details
          className={styles.disclosure}
          open={showUnavailable}
          onToggle={(e) =>
            setShowUnavailable((e.currentTarget as HTMLDetailsElement).open)
          }
        >
          <summary className={styles.summary}>
            <span>
              Other stores ({unavailable.length}) — not deliverable to your location
            </span>
            <span className={styles.summaryChevron} aria-hidden>
              {showUnavailable ? "▴" : "▾"}
            </span>
          </summary>
          <ul className={styles.list}>{unavailable.map(renderRow)}</ul>
        </details>
      )}
    </div>
  );
}
