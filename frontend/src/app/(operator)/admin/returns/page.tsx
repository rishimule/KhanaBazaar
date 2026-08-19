"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import AdminReturnsTable from "@/components/returns/AdminReturnsTable";

export default function AdminReturnsPage() {
  const t = useTranslations("Admin.returns");
  return (
    <div>
      <h1>{t("title")}</h1>
      <AdminReturnsTable />
    </div>
  );
}
