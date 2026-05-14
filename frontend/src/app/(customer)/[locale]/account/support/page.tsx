"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import { useState } from "react";
import { useTranslations } from "next-intl";
import styles from "./page.module.css";

const FAQ_KEYS = ["q1", "q2", "q3", "q4", "q5"] as const;

export default function SupportPage() {
  const t = useTranslations("Account.support");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);

  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    // Phase 1 stub — Phase 3 wires this to POST /api/v1/customers/me/support.
    console.log("[support] would send", { subject, message });
    setSent(true);
    setSubject("");
    setMessage("");
  };

  return (
    <div className={styles.page}>
      <section className={styles.section}>
        <h2 className={styles.title}>{t("faqTitle")}</h2>
        <p className={styles.subtitle}>{t("faqSubtitle")}</p>
        <div className={styles.faqList}>
          {FAQ_KEYS.map((k) => (
            <div key={k} className={styles.faqItem}>
              <div className={styles.faqQuestion}>{t(`faq.${k}.question`)}</div>
              <div className={styles.faqAnswer}>{t(`faq.${k}.answer`)}</div>
            </div>
          ))}
        </div>
      </section>
      <section className={styles.section}>
        <h2 className={styles.title}>{t("contactTitle")}</h2>
        <p className={styles.subtitle}>{t("contactSubtitle")}</p>
        <form className={styles.form} onSubmit={submit}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="subject">{t("subjectLabel")}</label>
            <input
              id="subject"
              className={styles.input}
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              required
              maxLength={120}
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="message">{t("messageLabel")}</label>
            <textarea
              id="message"
              className={styles.textarea}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              required
              maxLength={2000}
            />
          </div>
          <button className="btn btn-primary" type="submit">{t("send")}</button>
          {sent && <div className={styles.toast}>{t("sent")}</div>}
        </form>
      </section>
    </div>
  );
}
