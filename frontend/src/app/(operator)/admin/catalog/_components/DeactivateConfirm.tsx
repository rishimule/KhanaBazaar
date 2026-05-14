"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import Modal from "@/components/Modal";
import type { EntityKind } from "@/types";

function childLabel(entity: EntityKind): string {
  switch (entity) {
    case "service":
      return "categories";
    case "category":
      return "subcategories";
    case "subcategory":
      return "products";
    default:
      return "child rows";
  }
}

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
  return (
    <Modal
      title={`Deactivate "${name}"?`}
      onClose={onCancel}
      footer={
        <>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onCancel}
            disabled={pending}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-danger"
            onClick={onConfirm}
            disabled={pending}
          >
            {pending ? "Deactivating…" : "Deactivate"}
          </button>
        </>
      }
    >
      <p>
        This will hide <strong>{name}</strong> from customers
        {childCount > 0 ? (
          <>
            {" "}along with its {childCount} active {childLabel(entity)}
          </>
        ) : null}
        . You can re-activate it later.
      </p>
    </Modal>
  );
}
