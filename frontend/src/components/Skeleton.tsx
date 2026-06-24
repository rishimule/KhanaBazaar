// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import styles from "./Skeleton.module.css";

interface Props {
  width?: string | number;
  height?: string | number;
  radius?: string;
  className?: string;
}

/** Shimmer placeholder block. Decorative — marked aria-hidden; wrap the
 *  loading region in aria-busy="true" so assistive tech knows it's loading. */
export default function Skeleton({ width = "100%", height = 16, radius, className }: Props) {
  return (
    <span
      aria-hidden
      className={`${styles.skeleton}${className ? ` ${className}` : ""}`}
      style={{ width, height, borderRadius: radius }}
    />
  );
}
