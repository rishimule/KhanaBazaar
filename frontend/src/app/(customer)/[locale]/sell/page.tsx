// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { get } from "@/lib/api";
import type { Service } from "@/types";
import { Link as LocaleLink } from "@/i18n/navigation";
import FaqAccordion from "@/components/FaqAccordion";
import HowItWorksStepper from "./HowItWorksStepper";
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

  let services: Service[] = [];
  try {
    services = await get<Service[]>("/api/v1/catalog/services");
  } catch {
    services = [];
  }

  const whyItems = [
    { lead: t("why1Lead"), desc: t("why1Desc") },
    { lead: t("why2Lead"), desc: t("why2Desc") },
    { lead: t("why3Lead"), desc: t("why3Desc") },
    { lead: t("why4Lead"), desc: t("why4Desc") },
    { lead: t("why5Lead"), desc: t("why5Desc") },
  ];

  const steps = [
    { number: "01", title: t("step1Title"), body: t("step1Body") },
    { number: "02", title: t("step2Title"), body: t("step2Body") },
    { number: "03", title: t("step3Title"), body: t("step3Body") },
    { number: "04", title: t("step4Title"), body: t("step4Body") },
    { number: "05", title: t("step5Title"), body: t("step5Body") },
  ];

  const dashboardBlocks = [
    { title: t("dashSalesTitle"), items: [t("dashSalesItem1"), t("dashSalesItem2")] },
    {
      title: t("dashOrdersTitle"),
      items: [t("dashOrdersItem1"), t("dashOrdersItem2"), t("dashOrdersItem3")],
    },
    { title: t("dashCustomerTitle"), items: [t("dashCustomerItem1"), t("dashCustomerItem2")] },
    { title: t("dashAlertsTitle"), items: [t("dashAlertsItem1"), t("dashAlertsItem2")] },
  ];

  const checklistGroups = [
    {
      title: t("checklistGroup1Title"),
      items: [t("checklistGroup1Item1"), t("checklistGroup1Item2"), t("checklistGroup1Item3")],
    },
    {
      title: t("checklistGroup2Title"),
      items: [t("checklistGroup2Item1"), t("checklistGroup2Item2"), t("checklistGroup2Item3")],
    },
    {
      title: t("checklistGroup3Title"),
      items: [t("checklistGroup3Item1"), t("checklistGroup3Item2"), t("checklistGroup3Item3")],
    },
    {
      title: t("checklistGroup4Title"),
      items: [
        t("checklistGroup4Item1"),
        t("checklistGroup4Item2"),
        t("checklistGroup4Item3"),
        t("checklistGroup4Item4"),
        t("checklistGroup4Item5"),
        t("checklistGroup4Item6"),
      ],
    },
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
            {whyItems.map((item) => (
              <article key={item.lead} className={styles.valueCard}>
                <h3>{item.lead}</h3>
                <p>{item.desc}</p>
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
            <p className={styles.sectionSubtitle}>{t("howSubtitle")}</p>
          </div>

          <HowItWorksStepper steps={steps} />
        </div>
      </section>

      <section className={styles.section}>
        <div className="container">
          <div className={styles.sectionHeader}>
            <p className={styles.sectionKicker}>{t("categoriesKicker")}</p>
          </div>
          <div className={styles.categoryPath}>
            <h2 className={styles.categoryPathLabel}>{t("categoriesTitle")}</h2>
            {services.map((service) => (
              <span key={service.slug} className={styles.categoryPathItem}>
                <span className={styles.categoryPathSep} aria-hidden="true">
                  {">>"}
                </span>
                <span className={styles.categoryPathName}>{service.name}</span>
              </span>
            ))}
          </div>
        </div>
      </section>

      <section className={`${styles.section} ${styles.previewSection}`}>
        <div className="container">
          <div className={styles.sectionHeader}>
            <p className={styles.sectionKicker}>{t("previewKicker")}</p>
            <h2 className={styles.sectionTitle}>{t("previewTitle")}</h2>
            <p className={styles.sectionSubtitle}>{t("previewSubtitle")}</p>
            <p className={styles.previewBody}>{t("previewBody")}</p>
          </div>

          <div className={styles.dashboardGrid} aria-hidden="true">
            {dashboardBlocks.map((block) => (
              <article key={block.title} className={styles.dashboardBlock}>
                <h3 className={styles.dashboardBlockTitle}>{block.title}</h3>
                <ul className={styles.dashboardBlockList}>
                  {block.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className={styles.section}>
        <div className="container">
          <div className={styles.sectionHeader}>
            <p className={styles.sectionKicker}>{t("checklistKicker")}</p>
            <h2 className={styles.sectionTitle}>{t("checklistTitle")}</h2>
          </div>

          <div className={styles.checklistGroups}>
            {checklistGroups.map((group) => (
              <section key={group.title} className={styles.checklistGroup}>
                <h3 className={styles.checklistGroupTitle}>{group.title}</h3>
                <ul className={styles.checklist}>
                  {group.items.map((item) => (
                    <li key={item} className={styles.checklistItem}>
                      {item}
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </div>
      </section>

      <section className={`${styles.section} ${styles.sectionTint}`}>
        <div className="container">
          <div className={styles.sectionHeader}>
            <p className={styles.sectionKicker}>{t("faqKicker")}</p>
            <div className={styles.faqHeader}>
              <h2 className={styles.sectionTitle}>{t("faqTitle")}</h2>
              <LocaleLink href="/sell/faq" className={styles.faqMoreLink}>
                {t("moreFaq")}
              </LocaleLink>
            </div>
          </div>

          <FaqAccordion items={faqs} />
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
