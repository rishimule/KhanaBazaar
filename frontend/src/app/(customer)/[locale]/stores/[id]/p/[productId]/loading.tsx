// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import ProductDetailSkeleton from "@/components/ProductDetail/ProductDetailSkeleton";
import styles from "./ProductFullPage.module.css";

export default function Loading() {
  return (
    <main className={styles.page}>
      <ProductDetailSkeleton variant="page" />
    </main>
  );
}
