// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import type { Area } from "react-easy-crop";

/** Draw the cropped+rotated region of an image source to a canvas and return
 *  a Blob. `src` must be same-origin or a CORS-enabled URL (we set
 *  crossOrigin="anonymous") to avoid tainting the canvas. */
export async function getCroppedBlob(
  src: string,
  crop: Area,
  rotation: number,
): Promise<Blob> {
  const image = await loadImage(src);
  const rad = (rotation * Math.PI) / 180;

  // Bounding box of the rotated image.
  const bBoxW = Math.abs(Math.cos(rad) * image.width) + Math.abs(Math.sin(rad) * image.height);
  const bBoxH = Math.abs(Math.sin(rad) * image.width) + Math.abs(Math.cos(rad) * image.height);

  const tmp = document.createElement("canvas");
  tmp.width = bBoxW;
  tmp.height = bBoxH;
  const tctx = tmp.getContext("2d");
  if (!tctx) throw new Error("no_canvas_context");
  tctx.translate(bBoxW / 2, bBoxH / 2);
  tctx.rotate(rad);
  tctx.drawImage(image, -image.width / 2, -image.height / 2);

  const out = document.createElement("canvas");
  out.width = crop.width;
  out.height = crop.height;
  const octx = out.getContext("2d");
  if (!octx) throw new Error("no_canvas_context");
  octx.drawImage(
    tmp,
    crop.x, crop.y, crop.width, crop.height,
    0, 0, crop.width, crop.height,
  );

  return new Promise<Blob>((resolve, reject) => {
    out.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("blob_failed"))),
      "image/png",
    );
  });
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}
