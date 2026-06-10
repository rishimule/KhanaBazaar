"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useCallback, useState } from "react";
import Cropper, { type Area } from "react-easy-crop";
import Modal from "@/components/Modal";
import { getCroppedBlob } from "./cropImage";
import styles from "./ImageCropEditor.module.css";

interface Props {
  /** Object URL (local file) or CORS-enabled hosted URL. */
  src: string;
  onCancel: () => void;
  onDone: (blob: Blob) => void;
}

const ASPECTS: { label: string; value: number | undefined }[] = [
  { label: "1:1", value: 1 },
  { label: "4:3", value: 4 / 3 },
  { label: "Free", value: undefined },
];

export function ImageCropEditor({ src, onCancel, onDone }: Props) {
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [aspect, setAspect] = useState<number | undefined>(1);
  const [areaPx, setAreaPx] = useState<Area | null>(null);
  const [busy, setBusy] = useState(false);

  const onComplete = useCallback((_: Area, px: Area) => setAreaPx(px), []);

  async function handleDone() {
    if (!areaPx) return;
    setBusy(true);
    try {
      const blob = await getCroppedBlob(src, areaPx, rotation);
      onDone(blob);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Edit image"
      onClose={onCancel}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleDone}
            disabled={busy || !areaPx}
          >
            {busy ? "Applying…" : "Apply"}
          </button>
        </>
      }
    >
      <div className={styles.cropArea}>
        <Cropper
          image={src}
          crop={crop}
          zoom={zoom}
          rotation={rotation}
          aspect={aspect}
          onCropChange={setCrop}
          onZoomChange={setZoom}
          onRotationChange={setRotation}
          onCropComplete={onComplete}
        />
      </div>
      <div className={styles.controls}>
        <div className={styles.aspects}>
          {ASPECTS.map((a) => (
            <button
              key={a.label}
              type="button"
              className={aspect === a.value ? styles.aspectActive : styles.aspect}
              onClick={() => setAspect(a.value)}
            >
              {a.label}
            </button>
          ))}
        </div>
        <label className={styles.slider}>
          Zoom
          <input
            type="range"
            min={1}
            max={3}
            step={0.01}
            value={zoom}
            onChange={(e) => setZoom(Number(e.target.value))}
          />
        </label>
        <label className={styles.slider}>
          Rotate
          <input
            type="range"
            min={0}
            max={360}
            step={1}
            value={rotation}
            onChange={(e) => setRotation(Number(e.target.value))}
          />
        </label>
      </div>
    </Modal>
  );
}
