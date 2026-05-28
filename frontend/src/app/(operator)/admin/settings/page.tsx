"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import LanguagePreferenceCard from "@/components/LanguagePreferenceCard";
import styles from "./page.module.css";

export default function AdminSettingsPage() {
  const t = useTranslations("Admin.settings");
  const router = useRouter();
  const { dbUser, loading } = useAuth();

  useEffect(() => {
    if (!loading && (!dbUser || dbUser.role !== "admin")) {
      router.replace(dbUser ? "/" : "/login");
    }
  }, [loading, dbUser, router]);

  if (loading || !dbUser || dbUser.role !== "admin") {
    return null;
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>{t("title")}</h1>
      <LanguagePreferenceCard />
    </div>
  );
}
