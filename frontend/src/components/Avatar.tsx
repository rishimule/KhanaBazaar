"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useState } from "react";
import styles from "./Avatar.module.css";

interface Props {
  avatarUrl?: string | null;
  /** Display name — drives the initials fallback. */
  name: string;
  /** Stable seed (email / id) — drives the deterministic fallback color. */
  seed: string;
  size?: number;
}

function initialsAndColor(name: string, seed: string): { initials: string; color: string } {
  const parts = name.trim().split(/\s+/);
  const initials = (parts[0]?.charAt(0) ?? "") + (parts[1]?.charAt(0) ?? "");
  const hue = [...seed].reduce((a, c) => a + c.charCodeAt(0), 0) % 360;
  return { initials: (initials || "U").toUpperCase(), color: `hsl(${hue}deg 60% 50%)` };
}

export default function Avatar({ avatarUrl, name, seed, size = 64 }: Props) {
  // Track the URL that failed to load (not a bare boolean): when `avatarUrl`
  // changes after a replace, `failedUrl !== avatarUrl` is true again, so the
  // new image is retried with no effect/reset needed.
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const dim = { width: size, height: size, fontSize: Math.round(size * 0.4) };

  if (avatarUrl && failedUrl !== avatarUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={avatarUrl}
        alt={name}
        referrerPolicy="no-referrer"
        className={styles.avatar}
        style={dim}
        onError={() => setFailedUrl(avatarUrl)}
      />
    );
  }
  const { initials, color } = initialsAndColor(name, seed);
  return (
    <div className={styles.avatar} style={{ ...dim, background: color }}>
      {initials}
    </div>
  );
}
