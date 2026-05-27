"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useTranslations } from "next-intl";
import Modal from "@/components/Modal";
import type { EntityKind } from "@/types";

export function DeactivateConfirm({
  entity,
  name,
  childCount,
  onConfirm,
  onCancel,
  pending,
}: {
  entity: EntityKind;
  name: string;
  childCount: number;
  onConfirm: () => void;
  onCancel: () => void;
  pending?: boolean;
}) {
  const t = useTranslations("Admin.catalog");
  const tc = useTranslations("Admin.common");
  const childLabel = t(`entityPlural.${entity}`);
  return (
    <Modal
      title={t("deactivateTitle", { name })}
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
            className="btn btn-danger"
            onClick={onConfirm}
            disabled={pending}
          >
            {pending ? t("deactivating") : t("deactivate")}
          </button>
        </>
      }
    >
      <p>
        {childCount > 0
          ? t.rich("deactivateBodyWithChildren", {
              name,
              count: childCount,
              children: childLabel,
              strong: (chunks) => <strong>{chunks}</strong>,
            })
          : t.rich("deactivateBody", {
              name,
              strong: (chunks) => <strong>{chunks}</strong>,
            })}
      </p>
    </Modal>
  );
}
