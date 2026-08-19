"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { use } from "react";
import { useTranslations } from "next-intl";
import SellerReturnForm from "@/components/returns/SellerReturnForm";
import styles from "./page.module.css";

export default function SellerStartReturnPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const t = useTranslations("Seller.returns.initiate");

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>{t("title")}</h1>
      <p className={styles.subtitle}>{t("subtitle", { orderId: id })}</p>
      <SellerReturnForm orderId={Number(id)} />
    </div>
  );
}
