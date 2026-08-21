// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { getTranslations } from "next-intl/server";
import ReturnWizard from "@/components/returns/ReturnWizard";
import { get } from "@/lib/api";
import styles from "./page.module.css";

interface PolicyDocument {
  kind: string;
  version: number;
  body: string;
}

/** The published agreement, or null when none exists. The backend refuses to
 *  start a return without one, so the wizard surfaces that as an error rather
 *  than inventing terms here. */
async function loadAgreement(): Promise<string | null> {
  try {
    const doc = await get<PolicyDocument>("/api/v1/policies/return_agreement");
    return doc.body;
  } catch {
    return null;
  }
}

export default async function ReturnWizardPage({
  params,
}: {
  params: Promise<{ id: string; locale: string }>;
}) {
  const { id } = await params;
  const t = await getTranslations("Account.returns");
  const agreement = await loadAgreement();

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>{t("wizardTitle", { orderId: id })}</h1>
      <ReturnWizard orderId={Number(id)} agreementBody={agreement} />
    </div>
  );
}
