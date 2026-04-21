import type { Metadata } from "next";
import Link from "next/link";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Become a Seller",
  description:
    "Apply to sell on Khana Bazaar and bring your neighborhood store online for nearby shoppers.",
};

const valueCards = [
  {
    title: "Local reach",
    body: "Show your store to nearby shoppers who already look for daily essentials in your area.",
  },
  {
    title: "Inventory control",
    body: "Choose which products appear, set prices, and manage stock levels for your own storefront.",
  },
  {
    title: "Verified sellers",
    body: "Keep the marketplace trusted with a simple review step before your store goes live.",
  },
  {
    title: "Indian commerce ready",
    body: "Built for neighborhood businesses that sell across kirana, pharmacy, electronics, and general retail.",
  },
];

const steps = [
  "Verify your email",
  "Submit business details",
  "Wait for review",
  "Start selling",
];

const categories = [
  "Grocery and kirana",
  "Pharmacy and wellness",
  "Electronics accessories",
  "General stores",
];

const dashboardRows = [
  { name: "Daily essentials", stock: "In stock", visibility: "Shown on storefront" },
  { name: "Pharmacy items", stock: "Limited", visibility: "Visible with low stock" },
  { name: "Mobile accessories", stock: "In stock", visibility: "Available to nearby shoppers" },
];

const checklistItems = [
  "Verified email and mobile number",
  "Business name, category, and address",
  "GST number",
  "FSSAI license",
  "Bank account number and IFSC",
];

const faqs = [
  {
    question: "Is approval instant?",
    answer: "No. Applications are reviewed before approval, and most are completed within 1-2 business days.",
  },
  {
    question: "What documents do I need?",
    answer:
      "Keep your verified email and mobile number, business details, GST number, FSSAI license, and bank account information ready.",
  },
  {
    question: "What if my application is rejected?",
    answer:
      "You can fix the missing details or documents and submit the application again from the seller signup flow.",
  },
  {
    question: "What happens after approval?",
    answer:
      "You can publish your store, add products, manage stock, and set availability for nearby shoppers.",
  },
  {
    question: "Can I control products and prices?",
    answer:
      "Yes. You decide which products are visible, how they are priced, and when items should be marked unavailable.",
  },
  {
    question: "Which businesses are eligible?",
    answer:
      "Neighborhood stores such as kiranas, pharmacies, electronics shops, and general retail businesses can apply.",
  },
];

export default function SellPage() {
  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div className="container">
          <div className={styles.heroGrid}>
            <div className={styles.heroCopy}>
              <p className={styles.eyebrow}>For local stores</p>
              <h1 className={styles.heroTitle}>Bring your neighborhood store online</h1>
              <p className={styles.heroBody}>
                Reach nearby customers from your kirana, pharmacy, electronics counter, or
                general store while keeping control of your products, prices, and stock.
              </p>
              <p className={styles.reviewNote}>
                Seller applications are reviewed before stores go live and are usually
                completed within 1-2 business days.
              </p>
              <div className={styles.heroActions}>
                <Link href="/seller/signup" className="btn btn-primary">
                  Apply to sell
                </Link>
                <Link href="#how-it-works" className="btn btn-outline">
                  See how it works
                </Link>
              </div>
            </div>

            <div className={styles.storefrontVisual} aria-label="Stylized storefront illustration">
              <div className={styles.storefrontRoof} />
              <div className={styles.storefrontBody}>
                <div className={styles.storefrontSign}>
                  <span className={styles.signMark} />
                  <span>Neighborhood Storefront</span>
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
                  <span>Stocked shelves</span>
                  <span>Visible storefront</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className={styles.section}>
        <div className="container">
          <div className={styles.sectionHeader}>
            <p className={styles.sectionKicker}>Why sellers choose it</p>
            <h2 className={styles.sectionTitle}>Built for the way local stores already work</h2>
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
            <p className={styles.sectionKicker}>How it works</p>
            <h2 className={styles.sectionTitle}>A simple path from signup to selling</h2>
          </div>

          <div className={styles.stepsGrid}>
            {steps.map((step, index) => (
              <article key={step} className={styles.stepCard}>
                <span className={styles.stepNumber}>0{index + 1}</span>
                <h3>{step}</h3>
                <p>
                  {index === 0 && "Start by confirming the contact details tied to your application."}
                  {index === 1 && "Share the business information needed to review your store."}
                  {index === 2 && "Your application is checked before the store is approved."}
                  {index === 3 && "Once approved, you can publish products and manage availability."}
                </p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className={styles.section}>
        <div className="container">
          <div className={styles.sectionHeader}>
            <p className={styles.sectionKicker}>Store categories</p>
            <h2 className={styles.sectionTitle}>Start with the products your customers already ask for</h2>
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
                <p className={styles.sectionKicker}>Dashboard preview</p>
                <h2 className={styles.sectionTitle}>See the basics before you go live</h2>
              </div>
              <p className={styles.previewBody}>
                The seller dashboard keeps the focus on total products, store status, inventory,
                stock, availability, and storefront visibility.
              </p>
            </div>

            <div className={styles.dashboardMockup} aria-label="Dashboard preview mockup">
              <div className={styles.dashboardTopbar}>
                <span className={styles.dashboardStatusPill}>Store status: Pending review</span>
                <span className={styles.dashboardMetric}>Total products 24</span>
              </div>

              <div className={styles.dashboardPanel}>
                <div className={styles.dashboardPanelHeader}>
                  <span>Inventory snapshot</span>
                  <span>Store visibility on</span>
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
            <p className={styles.sectionKicker}>What to keep ready</p>
            <h2 className={styles.sectionTitle}>Checklist for your seller application</h2>
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
            <p className={styles.sectionKicker}>FAQ</p>
            <h2 className={styles.sectionTitle}>Common questions from store owners</h2>
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
              <h2 className={styles.finalTitle}>Ready to bring your store online?</h2>
              <p className={styles.finalBody}>
                Start your seller application and keep your business details ready.
              </p>
            </div>
            <Link href="/seller/signup" className="btn btn-primary">
              Start your seller application
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
