// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Link as LocaleLink } from "@/i18n/navigation";
import FaqAccordion from "@/components/FaqAccordion";
import styles from "../page.module.css";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Sell");
  return {
    title: t("faqMetaTitle"),
    description: t("faqMetaDescription"),
  };
}

export default async function SellFaqPage() {
  const t = await getTranslations("Sell");

  const faqs = [
    { question: t("faq1Q"), answer: t("faq1A") },
    { question: t("faq2Q"), answer: t("faq2A") },
    { question: t("faq3Q"), answer: t("faq3A") },
    { question: t("faq4Q"), answer: t("faq4A") },
    { question: t("faq5Q"), answer: t("faq5A") },
    { question: t("faq6Q"), answer: t("faq6A") },
    { question: t("faq7Q"), answer: t("faq7A") },
    { question: t("faq8Q"), answer: t("faq8A") },
    { question: t("faq9Q"), answer: t("faq9A") },
    { question: t("faq10Q"), answer: t("faq10A") },
    { question: t("faq11Q"), answer: t("faq11A") },
    { question: t("faq12Q"), answer: t("faq12A") },
    { question: t("faq13Q"), answer: t("faq13A") },
  ];

  return (
    <main className={styles.page}>
      <section className={styles.section}>
        <div className="container">
          <div className={styles.sectionHeader}>
            <h1 className={styles.sectionTitle}>{t("faqTitle")}</h1>
          </div>

          <FaqAccordion items={faqs} />

          <p className={styles.faqBack}>
            <LocaleLink href="/sell">{t("faqPageBack")}</LocaleLink>
          </p>
        </div>
      </section>
    </main>
  );
}
