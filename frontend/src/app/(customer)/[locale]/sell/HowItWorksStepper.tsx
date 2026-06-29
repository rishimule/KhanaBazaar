// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import styles from "./HowItWorksStepper.module.css";

export type HowItWorksStep = { number: string; title: string; body: string };

const ADVANCE_MS = 2400;
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function subscribeReducedMotion(callback: () => void) {
  const mq = window.matchMedia(REDUCED_MOTION_QUERY);
  mq.addEventListener("change", callback);
  return () => mq.removeEventListener("change", callback);
}

function getReducedMotionSnapshot() {
  return window.matchMedia(REDUCED_MOTION_QUERY).matches;
}

function getReducedMotionServerSnapshot() {
  return false;
}

export default function HowItWorksStepper({ steps }: { steps: HowItWorksStep[] }) {
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const reduced = useSyncExternalStore(
    subscribeReducedMotion,
    getReducedMotionSnapshot,
    getReducedMotionServerSnapshot,
  );

  useEffect(() => {
    if (paused || reduced || steps.length <= 1) return;
    const id = window.setInterval(
      () => setActive((i) => (i + 1) % steps.length),
      ADVANCE_MS,
    );
    return () => window.clearInterval(id);
  }, [paused, reduced, steps.length]);

  return (
    <div
      className={styles.stepper}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <ol className={styles.rail} aria-hidden="true">
        {steps.map((step, i) => (
          <li
            key={step.number}
            className={[
              styles.railNode,
              i === active ? styles.railNodeActive : "",
              i < active ? styles.railNodeDone : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            <span className={styles.railDot}>{step.number}</span>
          </li>
        ))}
      </ol>

      <div className={styles.cards}>
        {steps.map((step, i) => (
          <article
            key={step.number}
            className={`${styles.card} ${i === active ? styles.cardActive : ""}`}
          >
            <span className={styles.cardNumber}>{step.number}</span>
            <h3 className={styles.cardTitle}>{step.title}</h3>
            <p className={styles.cardBody}>{step.body}</p>
          </article>
        ))}
      </div>
    </div>
  );
}
