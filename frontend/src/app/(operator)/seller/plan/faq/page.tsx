// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import Link from "next/link";

import styles from "./page.module.css";

// Operator page — hardcoded English (fee subsystem copy is English-only).
const FAQ: { q: string; a: string }[] = [
  {
    q: "What is the platform fee?",
    a: "It's a per-service charge that keeps your store listed and able to take orders on the marketplace. Each service — Grocery, Pharmacy, and so on — has its own plan.",
  },
  {
    q: "Do I pay anything to start?",
    a: "No. Every new service begins on a free trial. You only pay if you choose a paid plan.",
  },
  {
    q: "What paid plans are available?",
    a: "Fixed-term subscriptions of 3, 6, or 12 months. The marketplace team sets the price for each service, and you'll see the current prices on your Plan page.",
  },
  {
    q: "How do I pay?",
    a: "Payments are made offline. Pick a plan, then pay using the UPI or bank details shown on your Plan page and tap “I've paid”. The team confirms the payment and activates your plan.",
  },
  {
    q: "When does my plan activate?",
    a: "As soon as the team confirms your payment. If you pay before your current term ends, the new term stacks on top of it. If you pay after a lapse, the term starts fresh from the confirmation date.",
  },
  {
    q: "What happens when my plan expires?",
    a: "You'll get reminders as the renewal date approaches. If it lapses, there's a short grace period, after which the service is suspended until you renew.",
  },
  {
    q: "What does suspension mean?",
    a: "A suspended service stops accepting new orders and is hidden from customers. Orders that were already placed are not affected. Renew to bring the service back.",
  },
  {
    q: "What do paid plans get me?",
    a: "A premium crown on your store, priority placement when customers compare prices, and access to advanced revenue reports.",
  },
  {
    q: "How do I cancel?",
    a: "Use “Cancel subscription” on the Plan page. Your plan stays active until the end of the paid term and then stops renewing — it isn't refunded.",
  },
];

export default function SellerPlanFaqPage() {
  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Fees &amp; Plans — FAQ</h1>
      <div className={styles.list}>
        {FAQ.map((item) => (
          <section className={styles.item} key={item.q}>
            <h2 className={styles.q}>{item.q}</h2>
            <p className={styles.a}>{item.a}</p>
          </section>
        ))}
      </div>
      <Link href="/seller/plan" className={styles.back}>
        ← Back to Plan
      </Link>
    </div>
  );
}
