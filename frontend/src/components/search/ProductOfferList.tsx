"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import { useCart } from "@/lib/CartContext";
import type { CompareOffer, CompareResponse } from "@/lib/searchClient";
import styles from "./ProductOfferList.module.css";

type Props = {
  data: CompareResponse;
};

export function ProductOfferList({ data }: Props) {
  const t = useTranslations("Search");
  const { addItem } = useCart();
  const { product, offers } = data;

  async function add(offer: CompareOffer) {
    if (!offer.is_available || !offer.is_serviceable || offer.stock <= 0) return;
    await addItem(
      offer.store.id,
      offer.store.name,
      product.service_id,
      "", // service name snapshot — backend re-snapshots from current locale on checkout
      {
        product_id: product.id,
        inventory_id: offer.inventory_id,
        product_name: product.name,
        quantity: 1,
        price: offer.price,
        image_url: product.image_url ?? undefined,
      }
    );
  }

  return (
    <ul className={styles.list}>
      {offers.map((o) => {
        const disabled = !o.is_available || !o.is_serviceable || o.stock <= 0;
        return (
          <li key={o.store.id} className={styles.row}>
            <div className={styles.storeMeta}>
              <div className={styles.storeName}>{o.store.name}</div>
              <div className={styles.subtext}>
                {o.store.distance_km !== null && (
                  <span>{o.store.distance_km} km · </span>
                )}
                {!o.is_serviceable && (
                  <span className={styles.warning}>
                    {t("notDeliverable")}
                  </span>
                )}
                {o.is_serviceable && !o.is_available && (
                  <span className={styles.warning}>{t("outOfStock")}</span>
                )}
              </div>
            </div>
            <div className={styles.price}>₹{o.price.toFixed(0)}</div>
            <button
              type="button"
              className={styles.addBtn}
              disabled={disabled}
              onClick={() => add(o)}
            >
              {t("add")}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
