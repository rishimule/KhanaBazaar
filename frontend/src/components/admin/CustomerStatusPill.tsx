"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useTranslations } from "next-intl";
import type { CustomerAccountStatus } from "@/types";
import styles from "./CustomerStatusPill.module.css";

const CLASS_BY_STATUS: Record<CustomerAccountStatus, string> = {
  active: styles.active,
  deactivated: styles.deactivated,
  suspended: styles.suspended,
  deleted: styles.deleted,
};

export default function CustomerStatusPill({
  status,
}: {
  status: CustomerAccountStatus;
}) {
  const t = useTranslations("Admin.customers.status");
  return (
    <span className={`${styles.pill} ${CLASS_BY_STATUS[status]}`}>
      {t(status)}
    </span>
  );
}
