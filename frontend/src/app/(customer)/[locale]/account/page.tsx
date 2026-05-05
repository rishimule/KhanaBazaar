"use client";
import { useTranslations } from "next-intl";
import ActiveOrdersWidget from "@/components/orders/ActiveOrdersWidget";

export default function AccountHomePage() {
  const t = useTranslations("Account");
  return (
    <div style={{ padding: "1.5rem", maxWidth: 1100, margin: "0 auto" }}>
      <h1>{t("dashboardTitle")}</h1>
      <ActiveOrdersWidget role="customer" limit={5} />
    </div>
  );
}
