// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useState } from "react";
import { useAuth } from "@/lib/AuthContext";
import { ApiError } from "@/lib/api";
import {
  createCatalog,
  deleteCatalog,
  updateCatalog,
  upsertTranslation,
} from "@/lib/catalog";
import type {
  CatalogEntity,
  CatalogEntityWrite,
  EntityKind,
  TranslationOut,
} from "@/types";

interface FieldError {
  detail: string;
  field?: string;
}

const SLUG_DETAILS = new Set(["slug_exists", "slug_exists_in_destination"]);

function extractError(e: unknown): FieldError {
  if (e instanceof ApiError) {
    // TODO(i18n): "Request failed" fallback is i18n-deferred — this is a
    // non-component hook so it cannot call useTranslations. Translate at the
    // component display site (Shared.requestFailed) when that page is i18n'd.
    const detail = e.detail || "Request failed";
    return {
      detail,
      field: SLUG_DETAILS.has(detail) ? "slug" : undefined,
    };
  }
  return { detail: e instanceof Error ? e.message : "Request failed" };
}

export function useEntityMutation(entity: EntityKind) {
  const { token } = useAuth();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<FieldError | null>(null);

  async function run<T>(op: () => Promise<T>): Promise<T | null> {
    setPending(true);
    setError(null);
    try {
      return await op();
    } catch (e) {
      setError(extractError(e));
      return null;
    } finally {
      setPending(false);
    }
  }

  return {
    pending,
    error,
    clearError: () => setError(null),
    create: (body: CatalogEntityWrite): Promise<CatalogEntity | null> =>
      run(() => createCatalog(entity, body, token)),
    update: (id: number, body: CatalogEntityWrite): Promise<CatalogEntity | null> =>
      run(() => updateCatalog(entity, id, body, token)),
    remove: (id: number): Promise<void | null> => run(() => deleteCatalog(entity, id, token)),
    upsertTrans: (id: number, body: TranslationOut): Promise<void | null> =>
      run(() => upsertTranslation(entity, id, body, token)),
  };
}
