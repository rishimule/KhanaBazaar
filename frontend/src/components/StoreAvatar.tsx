"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState } from "react";
import styles from "./StoreAvatar.module.css";

/**
 * Store card/header avatar. Renders the store logo image when `logoUrl` is set,
 * otherwise the uppercase initial. Falls back to the initial if the image fails
 * to load.
 *
 * Two sizing modes:
 * - `className` — pass the caller's existing avatar class (size/shape/colour).
 *   Used by store cards that already have a styled avatar box.
 * - `size` — a self-contained circular avatar of `size` px (background, colour,
 *   and font supplied inline). Used where no avatar class exists (e.g. the admin
 *   inline-styled screens).
 */
export default function StoreAvatar({
  name,
  logoUrl,
  className,
  size,
}: {
  name: string;
  logoUrl?: string | null;
  className?: string;
  size?: number;
}) {
  const [failed, setFailed] = useState(false);
  const initial = (name?.charAt(0) || "?").toUpperCase();
  const showImage = !!logoUrl && !failed;
  const cls = className ? `${styles.wrap} ${className}` : styles.wrap;
  const style: React.CSSProperties | undefined = size
    ? {
        width: size,
        height: size,
        borderRadius: "50%",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--color-neutral-100)",
        color: "var(--color-neutral-700)",
        fontWeight: 700,
        fontSize: Math.round(size * 0.4),
        flex: "0 0 auto",
      }
    : undefined;
  return (
    <span className={cls} style={style} aria-hidden>
      {showImage ? (
        <img
          src={logoUrl as string}
          alt=""
          referrerPolicy="no-referrer"
          className={styles.img}
          onError={() => setFailed(true)}
        />
      ) : (
        initial
      )}
    </span>
  );
}
