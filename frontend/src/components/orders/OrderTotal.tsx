"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useTranslations } from "next-intl";
import { courierChargePending, type CourierStatusFields } from "@/lib/courier";

/** An order's total for lists and cards. Before a courier quote is accepted
 *  the charge is not in `total`, so it reads "₹200.00 + courier". */
export default function OrderTotal({
  order,
  className,
}: {
  order: CourierStatusFields & { total: number };
  className?: string;
}) {
  const t = useTranslations("Order.card");
  const amount = order.total.toFixed(2);
  return (
    <span className={className}>
      {courierChargePending(order) ? t("totalPlusCourier", { amount }) : `₹${amount}`}
    </span>
  );
}
