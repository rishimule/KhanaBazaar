"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useTranslations } from "next-intl";
import ActiveOrdersWidget from "@/components/orders/ActiveOrdersWidget";

export default function AccountHomePage() {
  const t = useTranslations("Account");
  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", display: "flex", flexDirection: "column", gap: 20 }}>
      <h1 style={{
        fontSize: 24,
        fontWeight: 500,
        letterSpacing: "-0.20px",
        color: "var(--shade-cool-dark-7)",
        margin: 0,
      }}>{t("dashboardTitle")}</h1>
      <ActiveOrdersWidget role="customer" limit={5} />
    </div>
  );
}
