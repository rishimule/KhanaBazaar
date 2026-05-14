// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useTranslations } from "next-intl";
import Modal from "@/components/Modal";
import type { ComparisonAlternative } from "@/types";
import styles from "./SwitchStoreDialog.module.css";

interface Props {
  alternative: ComparisonAlternative;
  sourceStoreName: string;
  preExistingItemCount: number;
  submitting: boolean;
  errorKey: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function SwitchStoreDialog({
  alternative,
  sourceStoreName,
  preExistingItemCount,
  submitting,
  errorKey,
  onConfirm,
  onCancel,
}: Props) {
  const t = useTranslations("Checkout.compare");
  const tErr = useTranslations("Errors");

  const covered = alternative.items.filter((i) => !i.imputed);
  const missing = alternative.items.filter((i) => i.imputed);

  const errKey = errorKey?.startsWith("Errors.") ? errorKey.slice("Errors.".length) : errorKey;

  const guardedClose = () => {
    if (!submitting) onCancel();
  };

  return (
    <Modal
      title={t("dialogTitle", { store: alternative.name })}
      onClose={guardedClose}
      footer={
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.btnGhost}
            onClick={guardedClose}
            disabled={submitting}
          >
            {t("dialogCancel")}
          </button>
          <button
            type="button"
            className={styles.btnPrimary}
            onClick={onConfirm}
            disabled={submitting}
          >
            {submitting
              ? t("dialogSubmitting")
              : t("dialogConfirm", { store: alternative.name })}
          </button>
        </div>
      }
    >
      <div className={styles.dialog}>
        <p className={styles.lead}>
          {t("dialogLead", { count: covered.length, store: alternative.name })}
        </p>
        <ul className={styles.list}>
          {covered.map((i) => (
            <li key={i.product_id}>{i.product_name}</li>
          ))}
        </ul>

        {missing.length > 0 && (
          <>
            <p className={styles.lead}>
              {t("dialogMissing", { count: missing.length })}
            </p>
            <ul className={styles.list}>
              {missing.map((i) => (
                <li key={i.product_id}>{i.product_name}</li>
              ))}
            </ul>
          </>
        )}

        {preExistingItemCount > 0 && (
          <p className={styles.warning}>
            {t("dialogPreExisting", {
              count: preExistingItemCount,
              store: alternative.name,
            })}
          </p>
        )}

        <p className={styles.note}>
          {t("dialogSourcePreserved", { store: sourceStoreName })}
        </p>

        {errKey && (
          <p className={styles.error}>{tErr(errKey)}</p>
        )}
      </div>
    </Modal>
  );
}
