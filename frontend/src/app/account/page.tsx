"use client";
import ActiveOrdersWidget from "@/components/orders/ActiveOrdersWidget";

export default function AccountHomePage() {
  return (
    <div style={{ padding: "1.5rem", maxWidth: 1100, margin: "0 auto" }}>
      <h1>My account</h1>
      <ActiveOrdersWidget role="customer" limit={5} />
    </div>
  );
}
