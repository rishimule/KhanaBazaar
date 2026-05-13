// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import ProductDetailSkeleton from "@/components/ProductDetail/ProductDetailSkeleton";
import styles from "./ProductModal.module.css";

export default function Loading() {
  return (
    <div className={styles.backdrop}>
      <div className={styles.sheet}>
        <ProductDetailSkeleton variant="modal" />
      </div>
    </div>
  );
}
