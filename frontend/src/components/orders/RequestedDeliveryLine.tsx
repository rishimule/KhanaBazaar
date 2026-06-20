// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useLocale, useTranslations } from "next-intl";
import type { Order } from "@/types";
import {
  WINDOW_META,
  formatDateLabel,
  isDeliveryWindowKey,
} from "@/lib/deliveryWindows";

const LABEL_KEY: Record<string, string> = {
  morning: "windowMorning",
  afternoon: "windowAfternoon",
  evening: "windowEvening",
};

/** Renders "Requested delivery: Sat, 21 Jun · Evening (3–9 PM)" or null. */
export default function RequestedDeliveryLine({
  order,
  className,
}: {
  order: Pick<Order, "preferred_delivery_date" | "preferred_delivery_window">;
  className?: string;
}) {
  const t = useTranslations("Order.delivery");
  const locale = useLocale();
  const { preferred_delivery_date: date, preferred_delivery_window: win } = order;
  if (!date || !win || !isDeliveryWindowKey(win)) return null;
  const label = `${formatDateLabel(date, locale)} · ${t(LABEL_KEY[win])} (${WINDOW_META[win].hours})`;
  return (
    <p className={className}>
      {t("requested")}: {label}
    </p>
  );
}
