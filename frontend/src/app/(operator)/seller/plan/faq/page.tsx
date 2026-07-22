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
    a: "Fixed-term subscriptions of 3, 6, or 12 months, or pay-per-order where a small flat fee is charged for each order. The marketplace team sets the prices for each service, and you'll see the current options on your Plan page.",
  },
  {
    q: "How does pay-per-order work?",
    a: "You keep a prepaid balance. A fixed fee is deducted for each order you receive. When the balance runs low we warn you; top up before it runs out to keep taking orders.",
  },
  {
    q: "How do I top up my pay-per-order balance?",
    a: "Tap “Top up” on the Plan page, pay the amount offline via the UPI/bank details shown, and the team confirms it. Confirming a top-up reactivates your store straight away if it was paused for a low balance.",
  },
  {
    q: "What happens if my pay-per-order balance runs out?",
    a: "Your store enters a 2-day grace period so you can top up without interruption. If you don't top up within that window, the service is suspended until you add funds. Orders already placed are unaffected.",
  },
  {
    q: "Is a fee refunded if I cancel an order?",
    a: "Yes. If an order is cancelled, the per-order fee is credited straight back to your prepaid balance.",
  },
  {
    q: "What is store wallet credit?",
    a: "It's money the platform holds for you — for example, the leftover balance when you switch off pay-per-order. It's applied automatically towards future fees, or you can request it back from the marketplace team.",
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
    q: "What is the on-order-value (%) plan?",
    a: "A postpaid plan: instead of a fixed fee you pay a small percentage of your completed monthly sales for a service. You hold a refundable security deposit while you're on the plan.",
  },
  {
    q: "How is the order-value fee calculated and billed?",
    a: "At the start of each month we total the previous calendar month's completed (delivered) orders for the service and charge the agreed percentage. An invoice appears on your Plan page — by default on the 5th — with a due date to pay by.",
  },
  {
    q: "What is the security deposit for?",
    a: "It's held as collateral, not a prepayment. Your store activates once the team confirms the deposit, and it stays untouched unless fees go unpaid. It's refundable when you leave the plan.",
  },
  {
    q: "What happens if I miss a monthly order-value invoice?",
    a: "Each invoice has a due date followed by a short grace period. If it's still unpaid after that, the service is suspended until you clear it. Orders already placed are unaffected.",
  },
  {
    q: "Will my security deposit be returned?",
    a: "Yes. When you leave the plan the deposit is returned minus any outstanding fees — either back to you directly or as store wallet credit.",
  },
  {
    q: "Is GST included in the platform fees?",
    a: "Yes. All platform fees — subscriptions, pay-per-order, and the order-value percentage — are inclusive of GST as configured by the marketplace team.",
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
