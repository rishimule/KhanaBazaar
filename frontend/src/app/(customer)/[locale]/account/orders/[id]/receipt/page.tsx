// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { use } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import ReceiptScreen from "@/components/receipts/ReceiptScreen";

export default function CustomerReceiptPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const tStatus = useTranslations("Account.returns.status");
  return (
    <ReceiptScreen
      orderId={Number(id)}
      orderHref={`/account/orders/${id}`}
      returnHref={(returnId) => `/account/returns/${returnId}`}
      returnStatusLabel={(status) => tStatus(status)}
      renderLink={(href, label, className) => (
        <Link href={href} className={className}>
          {label}
        </Link>
      )}
    />
  );
}
