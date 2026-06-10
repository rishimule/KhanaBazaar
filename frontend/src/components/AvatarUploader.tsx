"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useRef, useState } from "react";
import dynamic from "next/dynamic";
import styles from "./AvatarUploader.module.css";

// Reuse the existing client-only crop editor from the product-image feature.
const ImageCropEditor = dynamic(
  () =>
    import("@/app/(operator)/admin/catalog/_components/ImageCropEditor").then(
      (m) => m.ImageCropEditor,
    ),
  { ssr: false },
);

interface Props {
  /** Receives the cropped blob; perform the API upload here. */
  onUpload: (blob: Blob) => Promise<void>;
  busy?: boolean;
  label?: string;
}

export default function AvatarUploader({ onUpload, busy, label = "Change picture" }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setError(null);
    setSrc(URL.createObjectURL(f));
    e.target.value = ""; // allow re-picking the same file
  }

  async function onDone(blob: Blob) {
    setSrc(null);
    try {
      await onUpload(blob);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    }
  }

  return (
    <div className={styles.wrap}>
      <button
        type="button"
        className={styles.pickBtn}
        onClick={() => inputRef.current?.click()}
        disabled={busy}
      >
        {busy ? "Uploading…" : label}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        hidden
        onChange={onPick}
      />
      {error && <p className={styles.error}>{error}</p>}
      {src && <ImageCropEditor src={src} onCancel={() => setSrc(null)} onDone={onDone} />}
    </div>
  );
}
