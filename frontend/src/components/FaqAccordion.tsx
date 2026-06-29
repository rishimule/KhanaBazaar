// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import styles from "./FaqAccordion.module.css";

export type FaqAccordionItem = { question: string; answer: string };

export default function FaqAccordion({ items }: { items: FaqAccordionItem[] }) {
  return (
    <div className={styles.list}>
      {items.map((item) => (
        <details key={item.question} className={styles.row}>
          <summary className={styles.summary}>
            <span className={styles.question}>{item.question}</span>
            <span className={styles.icon} aria-hidden="true" />
          </summary>
          <p className={styles.answer}>{item.answer}</p>
        </details>
      ))}
    </div>
  );
}
