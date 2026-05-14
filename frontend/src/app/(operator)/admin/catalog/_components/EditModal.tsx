"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState } from "react";
import Modal, { modalStyles } from "@/components/Modal";
import type {
  CatalogEntity,
  CatalogEntityWrite,
  EntityKind,
  TranslationOut,
} from "@/types";
import { useEntityMutation } from "../_hooks/useEntityMutation";
import { ParentPicker } from "./ParentPicker";
import { TranslationsAccordion } from "./TranslationsAccordion";
import styles from "./EditModal.module.css";

interface Props {
  entity: EntityKind;
  mode: "create" | "edit";
  initial?: CatalogEntity;
  parentId?: number;
  /** When creating subcategories: the service that contains the chosen
   * category. Used to scope the ParentPicker search to that service. */
  serviceContext?: number;
  onClose: () => void;
  onSaved: () => void;
}

function slugify(s: string): string {
  return s
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function parentEntityFor(entity: EntityKind): EntityKind | null {
  if (entity === "category") return "service";
  if (entity === "subcategory") return "category";
  if (entity === "product") return "subcategory";
  return null;
}

export function EditModal({
  entity,
  mode,
  initial,
  parentId,
  serviceContext,
  onClose,
  onSaved,
}: Props) {
  const mut = useEntityMutation(entity);
  const [name, setName] = useState(initial?.name || "");
  const [slug, setSlug] = useState(initial?.slug || "");
  const [slugDirty, setSlugDirty] = useState(false);
  const [description, setDescription] = useState(initial?.description || "");
  const [imageUrl, setImageUrl] = useState(initial?.image_url || "");
  const [basePrice, setBasePrice] = useState<number | "">(
    initial?.base_price ?? "",
  );
  const [brand, setBrand] = useState(initial?.brand || "");
  const [unit, setUnit] = useState(initial?.unit || "");
  const [isActive, setIsActive] = useState(initial?.is_active ?? true);
  const [parent, setParent] = useState<number | null>(
    initial?.service_id ??
      initial?.category_id ??
      initial?.subcategory_id ??
      parentId ??
      null,
  );
  const [translations, setTranslations] = useState<TranslationOut[]>(
    (initial?.translations || []).filter((t) => t.language_code !== "en"),
  );
  const [touchedLangs, setTouchedLangs] = useState<Set<string>>(new Set());

  function handleNameChange(v: string) {
    setName(v);
    if (mode === "create" && !slugDirty) {
      setSlug(slugify(v));
    }
  }

  function buildPayload(): CatalogEntityWrite {
    const body: CatalogEntityWrite = {
      name,
      slug: slug || undefined,
      description: description || null,
      image_url: imageUrl || null,
      is_active: isActive,
    };
    if (entity === "category") body.service_id = parent ?? undefined;
    if (entity === "subcategory") body.category_id = parent ?? undefined;
    if (entity === "product") {
      body.subcategory_id = parent ?? undefined;
      body.base_price = basePrice === "" ? undefined : Number(basePrice);
      body.brand = brand || null;
      body.unit = unit || null;
    }
    return body;
  }

  async function handleSave() {
    const body = buildPayload();
    const saved =
      mode === "create"
        ? await mut.create(body)
        : await mut.update(initial!.id, body);
    if (!saved) return;
    // Send every translation the user touched (empty values delete server-side).
    // Untouched langs are skipped entirely.
    for (const t of translations) {
      if (!touchedLangs.has(t.language_code)) continue;
      const result = await mut.upsertTrans(saved.id, t);
      if (result === null) {
        // mut.error is populated; keep modal open so user sees it.
        return;
      }
    }
    onSaved();
    onClose();
  }

  const parentEntity = parentEntityFor(entity);
  const parentFilter: { service_id?: number; category_id?: number } = {};
  if (entity === "subcategory" && serviceContext) {
    parentFilter.service_id = serviceContext;
  }

  return (
    <Modal
      title={`${mode === "create" ? "Create" : "Edit"} ${entity}`}
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
            disabled={mut.pending}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleSave}
            disabled={mut.pending || !name.trim()}
          >
            {mut.pending ? "Saving…" : "Save"}
          </button>
        </>
      }
    >
      <div className={styles.form}>
        <div className={modalStyles.formGroup}>
          <label className={modalStyles.label}>Name</label>
          <input
            className={modalStyles.input}
            type="text"
            value={name}
            onChange={(e) => handleNameChange(e.target.value)}
            autoFocus
          />
        </div>

        <div className={modalStyles.formGroup}>
          <label className={modalStyles.label}>Slug</label>
          <input
            className={modalStyles.input}
            type="text"
            value={slug}
            onChange={(e) => {
              setSlug(e.target.value);
              setSlugDirty(true);
            }}
          />
          {mut.error?.field === "slug" && (
            <p role="alert" className={styles.fieldError}>
              {mut.error.detail === "slug_exists"
                ? "Slug already used in this parent."
                : "Slug already used in destination parent."}
            </p>
          )}
        </div>

        <div className={modalStyles.formGroup}>
          <label className={modalStyles.label}>Description</label>
          <textarea
            className={modalStyles.textarea}
            value={description || ""}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        <div className={modalStyles.formGroup}>
          <label className={modalStyles.label}>Image URL</label>
          <input
            className={modalStyles.input}
            type="url"
            placeholder="https://…"
            value={imageUrl || ""}
            onChange={(e) => setImageUrl(e.target.value)}
          />
        </div>

        {parentEntity && (
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Parent {parentEntity}</label>
            <ParentPicker
              parentEntity={parentEntity}
              value={parent}
              onChange={setParent}
              filterParams={parentFilter}
            />
          </div>
        )}

        {entity === "product" && (
          <>
            <div className={modalStyles.formGroup}>
              <label className={modalStyles.label}>Base price</label>
              <input
                className={modalStyles.input}
                type="number"
                step="0.01"
                value={basePrice}
                onChange={(e) =>
                  setBasePrice(e.target.value === "" ? "" : Number(e.target.value))
                }
              />
            </div>
            <div className={modalStyles.formGroup}>
              <label className={modalStyles.label}>Brand</label>
              <input
                className={modalStyles.input}
                type="text"
                value={brand}
                onChange={(e) => setBrand(e.target.value)}
              />
            </div>
            <div className={modalStyles.formGroup}>
              <label className={modalStyles.label}>Unit (kg, L, pack…)</label>
              <input
                className={modalStyles.input}
                type="text"
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
              />
            </div>
          </>
        )}

        <div className={modalStyles.formGroup}>
          <label className={styles.checkbox}>
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
            />
            <span>Active</span>
          </label>
        </div>

        <div className={modalStyles.formGroup}>
          <TranslationsAccordion
            value={translations}
            onChange={setTranslations}
            onTouch={(code) =>
              setTouchedLangs((prev) => {
                if (prev.has(code)) return prev;
                const next = new Set(prev);
                next.add(code);
                return next;
              })
            }
          />
        </div>

        {mut.error && !mut.error.field && (
          <p role="alert" className={styles.formError}>
            {mut.error.detail}
          </p>
        )}
      </div>
    </Modal>
  );
}
