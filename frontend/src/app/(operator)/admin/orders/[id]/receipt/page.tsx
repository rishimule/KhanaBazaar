// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { use } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import ReceiptScreen from "@/components/receipts/ReceiptScreen";

export default function AdminReceiptPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const tStatus = useTranslations("Admin.returns.status");
  return (
    <ReceiptScreen
      orderId={Number(id)}
      orderHref={`/admin/orders/${id}`}
      returnHref={(returnId) => `/admin/returns/${returnId}`}
      returnStatusLabel={(status) => tStatus(status)}
      renderLink={(href, label, className) => (
        <Link href={href} className={className}>
          {label}
        </Link>
      )}
    />
  );
}
