"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import Lightbox from "yet-another-react-lightbox";
import Counter from "yet-another-react-lightbox/plugins/counter";
import Thumbnails from "yet-another-react-lightbox/plugins/thumbnails";
import Zoom from "yet-another-react-lightbox/plugins/zoom";
import "yet-another-react-lightbox/styles.css";
import "yet-another-react-lightbox/plugins/counter.css";
import "yet-another-react-lightbox/plugins/thumbnails.css";

interface ProductLightboxProps {
  slides: { src: string; alt: string }[];
  open: boolean;
  index: number;
  onClose: () => void;
  onIndexChange: (index: number) => void;
}

/** Fullscreen zoomable viewer. Default export so it can be next/dynamic'd with
 *  ssr:false — the library + its CSS then load only when first opened. */
export default function ProductLightbox({
  slides,
  open,
  index,
  onClose,
  onIndexChange,
}: ProductLightboxProps) {
  return (
    <Lightbox
      open={open}
      close={onClose}
      index={index}
      slides={slides}
      plugins={[Zoom, Thumbnails, Counter]}
      on={{ view: ({ index: i }) => onIndexChange(i) }}
      zoom={{ maxZoomPixelRatio: 3, scrollToZoom: true, doubleTapDelay: 250 }}
      thumbnails={{ position: "bottom", width: 72, height: 72, border: 0, gap: 8 }}
      carousel={{ finite: slides.length <= 1, padding: 0 }}
      controller={{ closeOnBackdropClick: true }}
      styles={{ container: { backgroundColor: "rgba(0,0,0,.92)" } }}
    />
  );
}
