"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import type { ReactNode } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import styles from "./ProfileSectionCard.module.css";

interface Props {
  title: string;
  editHref?: string;
  editLabel?: string;
  children: ReactNode;
}

export default function ProfileSectionCard({
  title,
  editHref,
  editLabel,
  children,
}: Props) {
  const t = useTranslations("Shared");
  const label = editLabel ?? t("edit");
  return (
    <section className={styles.card}>
      <header className={styles.cardHeader}>
        <h2 className={styles.cardTitle}>{title}</h2>
        {editHref && (
          <Link
            href={editHref}
            className={styles.editLink}
            aria-label={`${label} ${title}`}
          >
            {label}
          </Link>
        )}
      </header>
      <div className={styles.cardBody}>{children}</div>
    </section>
  );
}
