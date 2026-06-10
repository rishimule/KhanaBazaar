"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useAuth } from "@/lib/AuthContext";
import { ApiError } from "@/lib/api";
import {
  addProductImageUrl,
  deleteProductImage,
  reorderProductImages,
  uploadProductImage,
} from "@/lib/productImages";
import type { ProductImage } from "@/types";
import styles from "./ProductImageManager.module.css";

// Editor is client-only (canvas/DOM); never SSR it.
const ImageCropEditor = dynamic(
  () => import("./ImageCropEditor").then((m) => m.ImageCropEditor),
  { ssr: false },
);

const MAX_IMAGES = 20;
const MAX_MB = 10;
const ALLOWED = ["image/jpeg", "image/png", "image/webp"];

interface Props {
  productId: number;
  initial: ProductImage[];
}

export function ProductImageManager({ productId, initial }: Props) {
  const { token } = useAuth();
  const [images, setImages] = useState<ProductImage[]>(initial);
  const [urlInput, setUrlInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editSrc, setEditSrc] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const full = images.length >= MAX_IMAGES;

  function reportError(e: unknown) {
    setError(e instanceof ApiError ? e.detail : "Request failed");
  }

  async function doUpload(blob: Blob) {
    setBusy(true);
    setError(null);
    try {
      const created = await uploadProductImage(productId, blob, token);
      setImages((prev) => [...prev, created]);
    } catch (e) {
      reportError(e);
    } finally {
      setBusy(false);
    }
  }

  function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-picking same file
    if (!file) return;
    if (!ALLOWED.includes(file.type)) {
      setError("Only JPEG, PNG, or WebP images are allowed.");
      return;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`Image must be under ${MAX_MB} MB.`);
      return;
    }
    setEditSrc(URL.createObjectURL(file));
  }

  async function onAddUrl() {
    const url = urlInput.trim();
    if (!url) return;
    setBusy(true);
    setError(null);
    try {
      const created = await addProductImageUrl(productId, url, token);
      setImages((prev) => [...prev, created]);
      setUrlInput("");
    } catch (e) {
      reportError(e);
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(id?: number) {
    if (id === undefined) return;
    setBusy(true);
    setError(null);
    try {
      await deleteProductImage(productId, id, token);
      setImages((prev) => prev.filter((i) => i.id !== id));
    } catch (e) {
      reportError(e);
    } finally {
      setBusy(false);
    }
  }

  async function move(idx: number, dir: -1 | 1) {
    const next = [...images];
    const target = idx + dir;
    if (target < 0 || target >= next.length) return;
    [next[idx], next[target]] = [next[target], next[idx]];
    const prevImages = images;
    setImages(next);
    setBusy(true);
    setError(null);
    try {
      const ids = next
        .map((i) => i.id)
        .filter((v): v is number => v !== undefined);
      const saved = await reorderProductImages(productId, ids, token);
      setImages(saved);
    } catch (e) {
      reportError(e);
      setImages(prevImages); // revert
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.grid}>
        {images.map((img, idx) => (
          <div key={img.id ?? img.url} className={styles.cell}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={img.url} alt="" className={styles.thumb} referrerPolicy="no-referrer" />
            {idx === 0 && <span className={styles.coverBadge}>Cover</span>}
            <div className={styles.cellActions}>
              <button
                type="button"
                onClick={() => move(idx, -1)}
                disabled={busy || idx === 0}
                aria-label="Move left"
              >
                ←
              </button>
              <button
                type="button"
                onClick={() => move(idx, 1)}
                disabled={busy || idx === images.length - 1}
                aria-label="Move right"
              >
                →
              </button>
              <button
                type="button"
                onClick={() => onDelete(img.id)}
                disabled={busy}
                aria-label="Remove"
              >
                ✕
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className={styles.addRow}>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => fileRef.current?.click()}
          disabled={busy || full}
        >
          {busy ? "Working…" : "Upload image"}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          hidden
          onChange={onPickFile}
        />
      </div>

      <div className={styles.urlRow}>
        <input
          type="url"
          placeholder="https://… (paste an image URL)"
          value={urlInput}
          onChange={(e) => setUrlInput(e.target.value)}
          disabled={busy || full}
        />
        <button
          type="button"
          className="btn btn-secondary"
          onClick={onAddUrl}
          disabled={busy || full || !urlInput.trim()}
        >
          Add URL
        </button>
      </div>

      {full && <p className={styles.note}>Maximum of {MAX_IMAGES} images reached.</p>}
      {error && (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      )}

      {editSrc && (
        <ImageCropEditor
          src={editSrc}
          onCancel={() => {
            URL.revokeObjectURL(editSrc);
            setEditSrc(null);
          }}
          onDone={(blob) => {
            URL.revokeObjectURL(editSrc);
            setEditSrc(null);
            void doUpload(blob);
          }}
        />
      )}
    </div>
  );
}
