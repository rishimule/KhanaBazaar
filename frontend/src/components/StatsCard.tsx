// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import styles from "./StatsCard.module.css";

interface Props {
  icon: string;
  label: string;
  value: string | number;
  trend?: string;
  trendDirection?: "up" | "down";
  variant?: "primary" | "accent" | "info" | "warning";
}

export default function StatsCard({
  icon,
  label,
  value,
  trend,
  trendDirection,
  variant = "primary",
}: Props) {
  const iconClass = {
    primary: styles.iconPrimary,
    accent: styles.iconAccent,
    info: styles.iconInfo,
    warning: styles.iconWarning,
  }[variant];

  return (
    <div className={styles.card}>
      <div className={`${styles.iconWrap} ${iconClass}`}>{icon}</div>
      <div className={styles.info}>
        <span className={styles.label}>{label}</span>
        <span className={styles.value}>{value}</span>
        {trend && (
          <span
            className={`${styles.trend} ${
              trendDirection === "up" ? styles.trendUp : styles.trendDown
            }`}
          >
            {trendDirection === "up" ? "↑" : "↓"} {trend}
          </span>
        )}
      </div>
    </div>
  );
}
