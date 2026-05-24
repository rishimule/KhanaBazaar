"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import styles from "./ScrollRail.module.css";

type Props = {
  children: ReactNode;
  ariaLabel?: string;
  leftLabel?: string;
  rightLabel?: string;
};

export function ScrollRail({
  children,
  ariaLabel,
  leftLabel = "Scroll left",
  rightLabel = "Scroll right",
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [canLeft, setCanLeft] = useState(false);
  const [canRight, setCanRight] = useState(false);

  const update = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    setCanLeft(el.scrollLeft > 1);
    setCanRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
  }, []);

  useEffect(() => {
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [update, children]);

  const scroll = (dir: -1 | 1) => {
    const el = ref.current;
    if (!el) return;
    el.scrollBy({ left: dir * el.clientWidth * 0.8, behavior: "smooth" });
  };

  return (
    <div className={styles.wrap}>
      {canLeft && (
        <button
          type="button"
          className={`${styles.arrow} ${styles.arrowLeft}`}
          onClick={() => scroll(-1)}
          aria-label={leftLabel}
        >
          ‹
        </button>
      )}
      <div
        ref={ref}
        onScroll={update}
        className={styles.rail}
        aria-label={ariaLabel}
        role={ariaLabel ? "group" : undefined}
      >
        {children}
      </div>
      {canRight && (
        <button
          type="button"
          className={`${styles.arrow} ${styles.arrowRight}`}
          onClick={() => scroll(1)}
          aria-label={rightLabel}
        >
          ›
        </button>
      )}
    </div>
  );
}
