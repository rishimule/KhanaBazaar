"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import Modal from "@/components/Modal";
import type { EntityKind } from "@/types";

/** Confirmation for the multi-select activate/deactivate bar.
 *
 * Mirrors `DeactivateConfirm` (the per-row equivalent) including the child
 * warning: like the per-row button, a bulk deactivate does NOT cascade, so the
 * child count is surfaced rather than acted on. */
export function BulkStatusConfirm({
  entity,
  count,
  childCount,
  nextActive,
  pending,
  onConfirm,
  onCancel,
}: {
  entity: EntityKind;
  count: number;
  childCount: number;
  nextActive: boolean;
  pending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const t = useTranslations("Admin.catalog");
  const tc = useTranslations("Admin.common");
  const childLabel = t(`entityPlural.${entity}`);

  return (
    <Modal
      title={
        nextActive
          ? t("bulkConfirmActivateTitle", { count })
          : t("bulkConfirmDeactivateTitle", { count })
      }
      onClose={onCancel}
      footer={
        <>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onCancel}
            disabled={pending}
          >
            {tc("cancel")}
          </button>
          <button
            type="button"
            className={nextActive ? "btn btn-primary" : "btn btn-danger"}
            onClick={onConfirm}
            disabled={pending}
          >
            {pending
              ? tc("saving")
              : nextActive
                ? t("bulkActivate")
                : t("bulkDeactivate")}
          </button>
        </>
      }
    >
      <p>
        {nextActive
          ? t("bulkConfirmActivateBody", { count })
          : t("bulkConfirmDeactivateBody", { count })}
      </p>
      {!nextActive && childCount > 0 && (
        <p>{t("bulkChildWarning", { count: childCount, children: childLabel })}</p>
      )}
    </Modal>
  );
}
