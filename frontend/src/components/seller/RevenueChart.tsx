"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useEffect, useState } from "react";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import type { RevenueSeries } from "@/types";
import styles from "./RevenueChart.module.css";

type Range = "7d" | "14d" | "30d";
const RANGES: Range[] = ["7d", "14d", "30d"];

const W = 560;
const H = 200;
const PAD_X = 8;
const PAD_TOP = 12;
const PAD_BOTTOM = 22;

// Catmull-Rom → cubic-bezier smoothing over [x,y] points.
function smoothPath(pts: [number, number][]): string {
  if (pts.length === 0) return "";
  if (pts.length === 1) return `M ${pts[0][0]} ${pts[0][1]}`;
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] ?? pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] ?? p2;
    const c1x = p1[0] + (p2[0] - p0[0]) / 6;
    const c1y = p1[1] + (p2[1] - p0[1]) / 6;
    const c2x = p2[0] - (p3[0] - p1[0]) / 6;
    const c2y = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C ${c1x} ${c1y}, ${c2x} ${c2y}, ${p2[0]} ${p2[1]}`;
  }
  return d;
}

export default function RevenueChart() {
  const { token } = useAuth();
  const [range, setRange] = useState<Range>("14d");
  const [data, setData] = useState<RevenueSeries | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    setError(false);
    get<RevenueSeries>(`/api/v1/sellers/me/revenue-series?range=${range}`, token)
      .then(setData)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [token, range]);

  const points = data?.points ?? [];
  const govs = points.map((p) => p.gov);
  const max = Math.max(1, ...govs);
  const innerW = W - PAD_X * 2;
  const innerH = H - PAD_TOP - PAD_BOTTOM;
  const xy: [number, number][] = points.map((p, i) => {
    const x = PAD_X + (points.length <= 1 ? innerW / 2 : (i / (points.length - 1)) * innerW);
    const y = PAD_TOP + innerH - (p.gov / max) * innerH;
    return [x, y];
  });
  const line = smoothPath(xy);
  const area =
    xy.length > 0
      ? `${line} L ${xy[xy.length - 1][0]} ${PAD_TOP + innerH} L ${xy[0][0]} ${PAD_TOP + innerH} Z`
      : "";
  const labelStep = Math.max(1, Math.ceil(points.length / 7));

  return (
    <section className={styles.card}>
      <div className={styles.head}>
        <div>
          <h2 className={styles.title}>Revenue overview</h2>
          <p className={styles.sub}>Gross order value over time</p>
        </div>
        <div className={styles.toggle} role="tablist">
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              className={r === range ? styles.toggleOn : styles.toggleBtn}
              onClick={() => setRange(r)}
            >
              {r.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {data && (
        <div className={styles.stats}>
          <span>
            Avg / day <strong>₹{data.avg_per_day.toFixed(0)}</strong>
          </span>
          <span>
            Peak <strong>₹{data.peak.toFixed(0)}</strong>
          </span>
        </div>
      )}

      {error ? (
        <div className={styles.empty}>Couldn&apos;t load chart.</div>
      ) : loading ? (
        <div className={styles.empty}>Loading…</div>
      ) : govs.every((g) => g === 0) ? (
        <div className={styles.empty}>No revenue in this window yet.</div>
      ) : (
        <svg className={styles.svg} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
          <defs>
            <linearGradient id="revFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--color-primary)" stopOpacity="0.25" />
              <stop offset="100%" stopColor="var(--color-primary)" stopOpacity="0" />
            </linearGradient>
          </defs>
          {[0.25, 0.5, 0.75].map((g) => (
            <line
              key={g}
              x1={PAD_X}
              x2={W - PAD_X}
              y1={PAD_TOP + innerH * g}
              y2={PAD_TOP + innerH * g}
              className={styles.grid}
            />
          ))}
          <path d={area} fill="url(#revFill)" />
          <path d={line} className={styles.linePath} />
          {points.map((p, i) =>
            i % labelStep === 0 ? (
              <text key={p.date} x={xy[i][0]} y={H - 6} className={styles.axis} textAnchor="middle">
                {p.date.slice(8)}
              </text>
            ) : null
          )}
        </svg>
      )}
    </section>
  );
}
