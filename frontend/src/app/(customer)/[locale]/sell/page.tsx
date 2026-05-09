// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import styles from "./page.module.css";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Sell");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
  };
}

export default async function SellPage() {
  const t = await getTranslations("Sell");

  const valueCards = [
    { title: t("valueLocalReachTitle"), body: t("valueLocalReachBody") },
    { title: t("valueInventoryTitle"), body: t("valueInventoryBody") },
    { title: t("valueVerifiedTitle"), body: t("valueVerifiedBody") },
    { title: t("valueCommerceTitle"), body: t("valueCommerceBody") },
  ];

  const steps = [
    { title: t("step1Title"), body: t("step1Body") },
    { title: t("step2Title"), body: t("step2Body") },
    { title: t("step3Title"), body: t("step3Body") },
    { title: t("step4Title"), body: t("step4Body") },
  ];

  const categories = [
    t("categoryGrocery"),
    t("categoryPharmacy"),
    t("categoryElectronics"),
    t("categoryGeneral"),
  ];

  const dashboardRows = [
    { name: t("rowDailyName"), stock: t("rowDailyStock"), visibility: t("rowDailyVisibility") },
    { name: t("rowPharmacyName"), stock: t("rowPharmacyStock"), visibility: t("rowPharmacyVisibility") },
    { name: t("rowMobileName"), stock: t("rowMobileStock"), visibility: t("rowMobileVisibility") },
  ];

  const checklistItems = [
    t("checklistEmail"),
    t("checklistBusiness"),
    t("checklistGst"),
    t("checklistFssai"),
    t("checklistBank"),
  ];

  const faqs = [
    { question: t("faq1Q"), answer: t("faq1A") },
    { question: t("faq2Q"), answer: t("faq2A") },
    { question: t("faq3Q"), answer: t("faq3A") },
    { question: t("faq4Q"), answer: t("faq4A") },
    { question: t("faq5Q"), answer: t("faq5A") },
    { question: t("faq6Q"), answer: t("faq6A") },
  ];

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div className="container">
          <div className={styles.heroGrid}>
            <div className={styles.heroCopy}>
              <p className={styles.eyebrow}>{t("heroEyebrow")}</p>
              <h1 className={styles.heroTitle}>{t("heroTitle")}</h1>
              <p className={styles.heroBody}>{t("heroBody")}</p>
              <p className={styles.reviewNote}>{t("reviewNote")}</p>
              <div className={styles.heroActions}>
                <Link href="/seller/signup" className="btn btn-primary">
                  {t("applyToSell")}
                </Link>
                <Link href="#how-it-works" className="btn btn-outline">
                  {t("seeHowItWorks")}
                </Link>
              </div>
            </div>

            <div className={styles.storefrontVisual} aria-hidden="true">
              <div className={styles.storefrontRoof} />
              <div className={styles.storefrontBody}>
                <div className={styles.storefrontSign}>
                  <span className={styles.signMark} />
                  <span>{t("storefrontSign")}</span>
                </div>
                <div className={styles.storefrontWindow}>
                  <div className={styles.windowShelf}>
                    <span />
                    <span />
                    <span />
                  </div>
                  <div className={styles.windowShelf}>
                    <span />
                    <span />
                    <span />
                  </div>
                  <div className={styles.windowShelf}>
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
                <div className={styles.storefrontCounter}>
                  <span>{t("storefrontShelves")}</span>
                  <span>{t("storefrontVisible")}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className={styles.section}>
        <div className="container">
          <div className={styles.sectionHeader}>
            <p className={styles.sectionKicker}>{t("whyKicker")}</p>
            <h2 className={styles.sectionTitle}>{t("whyTitle")}</h2>
          </div>

          <div className={styles.valueGrid}>
            {valueCards.map((card) => (
              <article key={card.title} className={styles.valueCard}>
                <h3>{card.title}</h3>
                <p>{card.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className={`${styles.section} ${styles.sectionTint}`} id="how-it-works">
        <div className="container">
          <div className={styles.sectionHeader}>
            <p className={styles.sectionKicker}>{t("howKicker")}</p>
            <h2 className={styles.sectionTitle}>{t("howTitle")}</h2>
          </div>

          <div className={styles.stepsGrid}>
            {steps.map((step, index) => (
              <article key={step.title} className={styles.stepCard}>
                <span className={styles.stepNumber}>0{index + 1}</span>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className={styles.section}>
        <div className="container">
          <div className={styles.sectionHeader}>
            <p className={styles.sectionKicker}>{t("categoriesKicker")}</p>
            <h2 className={styles.sectionTitle}>{t("categoriesTitle")}</h2>
          </div>

          <div className={styles.categoryGrid}>
            {categories.map((category) => (
              <article key={category} className={styles.categoryCard}>
                <h3>{category}</h3>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className={`${styles.section} ${styles.previewSection}`}>
        <div className="container">
          <div className={styles.previewGrid}>
            <div className={styles.previewCopy}>
              <div className={styles.sectionHeader}>
                <p className={styles.sectionKicker}>{t("previewKicker")}</p>
                <h2 className={styles.sectionTitle}>{t("previewTitle")}</h2>
              </div>
              <p className={styles.previewBody}>{t("previewBody")}</p>
            </div>

            <div className={styles.dashboardMockup} aria-hidden="true">
              <div className={styles.dashboardTopbar}>
                <span className={styles.dashboardStatusPill}>{t("dashboardStatus")}</span>
                <span className={styles.dashboardMetric}>{t("dashboardTotal")}</span>
              </div>

              <div className={styles.dashboardPanel}>
                <div className={styles.dashboardPanelHeader}>
                  <span>{t("dashboardSnapshot")}</span>
                  <span>{t("dashboardVisibility")}</span>
                </div>
                <div className={styles.dashboardTable}>
                  {dashboardRows.map((row) => (
                    <div key={row.name} className={styles.dashboardRow}>
                      <span className={styles.dashboardRowName}>{row.name}</span>
                      <span>{row.stock}</span>
                      <span>{row.visibility}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className={styles.section}>
        <div className="container">
          <div className={styles.sectionHeader}>
            <p className={styles.sectionKicker}>{t("checklistKicker")}</p>
            <h2 className={styles.sectionTitle}>{t("checklistTitle")}</h2>
          </div>

          <ul className={styles.checklist}>
            {checklistItems.map((item) => (
              <li key={item} className={styles.checklistItem}>
                {item}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className={`${styles.section} ${styles.sectionTint}`}>
        <div className="container">
          <div className={styles.sectionHeader}>
            <p className={styles.sectionKicker}>{t("faqKicker")}</p>
            <h2 className={styles.sectionTitle}>{t("faqTitle")}</h2>
          </div>

          <div className={styles.faqList}>
            {faqs.map((faq) => (
              <article key={faq.question} className={styles.faqRow}>
                <h3>{faq.question}</h3>
                <p>{faq.answer}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className={styles.finalCta}>
        <div className="container">
          <div className={styles.finalCtaInner}>
            <div>
              <h2 className={styles.finalTitle}>{t("finalTitle")}</h2>
              <p className={styles.finalBody}>{t("finalBody")}</p>
            </div>
            <Link href="/seller/signup" className="btn btn-primary">
              {t("finalCta")}
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
