// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import styles from "./ProductDetail.module.css";

export default function ProductDetailSkeleton({ variant }: { variant: "modal" | "page" }) {
  return (
    <article className={`${styles.detail} ${styles[variant]}`} aria-busy>
      <div className={styles.imageWrap} aria-hidden />
      <div className={styles.body}>
        <div style={{ width: "70%", height: 24, background: "#e4e4e7", borderRadius: 6 }} />
        <div style={{ width: "50%", height: 14, background: "#e4e4e7", borderRadius: 6 }} />
        <div style={{ width: "30%", height: 22, background: "#e4e4e7", borderRadius: 6 }} />
        <div style={{ width: 80, height: 22, background: "#e4e4e7", borderRadius: 999 }} />
      </div>
    </article>
  );
}
