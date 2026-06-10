"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import type { ProductImage } from "@/types";
import styles from "./ProductGallery.module.css";

// Library + its CSS load only when the viewer first opens.
const ProductLightbox = dynamic(() => import("./ProductLightbox"), { ssr: false });

interface ProductGalleryProps {
  images: ProductImage[];
  imageUrl?: string;
  productName: string;
  variant: "modal" | "page";
}

export default function ProductGallery({
  images,
  imageUrl,
  productName,
  variant,
}: ProductGalleryProps) {
  const t = useTranslations("Product");
  const gallery =
    images.length > 0 ? images : imageUrl ? [{ url: imageUrl, position: 0 }] : [];

  const [activeIdx, setActiveIdx] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [failed, setFailed] = useState<Record<number, boolean>>({});
  const trackRef = useRef<HTMLDivElement>(null);
  const slideRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // Sync the active index from whichever slide is centered in the track
  // (covers both touch-swipe and programmatic scroll from rail/dots).
  useEffect(() => {
    const track = trackRef.current;
    if (!track || gallery.length <= 1) return;
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting && e.intersectionRatio >= 0.6) {
            const idx = Number((e.target as HTMLElement).dataset.idx);
            if (!Number.isNaN(idx)) setActiveIdx(idx);
          }
        }
      },
      { root: track, threshold: 0.6 },
    );
    slideRefs.current.forEach((el) => el && obs.observe(el));
    return () => obs.disconnect();
  }, [gallery.length]);

  // When the fullscreen viewer closes (possibly on a different image than it
  // opened on), bring the inline track in line with activeIdx so the rail/dots
  // and the visible slide stay in agreement.
  useEffect(() => {
    if (lightboxOpen) return;
    const track = trackRef.current;
    if (track) track.scrollTo({ left: activeIdx * track.clientWidth, behavior: "auto" });
  }, [activeIdx, lightboxOpen]);

  function goTo(i: number) {
    setActiveIdx(i);
    slideRefs.current[i]?.scrollIntoView({
      behavior: "smooth",
      inline: "center",
      block: "nearest",
    });
  }

  if (gallery.length === 0) {
    return (
      <div className={`${styles.media} ${styles[variant]}`}>
        <div className={styles.stage}>
          <div className={styles.track}>
            <div className={styles.slide}>
              <span className={styles.placeholder} aria-hidden>📦</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const slides = gallery.map((g, i) => ({
    src: g.url,
    alt: `${productName} – image ${i + 1}`,
  }));
  const multi = gallery.length > 1;

  return (
    <div className={`${styles.media} ${styles[variant]}`}>
      {multi && (
        <div className={styles.rail} role="group" aria-label={t("imageGallery")}>
          {gallery.map((g, i) => (
            <button
              key={`${i}-${g.url}`}
              type="button"
              className={i === activeIdx ? styles.thumbActive : styles.thumb}
              aria-label={`${productName} – image ${i + 1}`}
              aria-current={i === activeIdx}
              onClick={() => goTo(i)}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={g.url} alt="" referrerPolicy="no-referrer" />
            </button>
          ))}
        </div>
      )}

      <div className={styles.stage}>
        <div
          ref={trackRef}
          className={styles.track}
          role={multi ? "group" : undefined}
          aria-roledescription={multi ? "carousel" : undefined}
        >
          {gallery.map((g, i) => (
            <button
              key={`${i}-${g.url}`}
              type="button"
              ref={(el) => {
                slideRefs.current[i] = el;
              }}
              data-idx={i}
              className={styles.slide}
              aria-label={`${productName} – image ${i + 1}, ${t("openZoom")}`}
              onClick={() => {
                if (!failed[i]) setLightboxOpen(true);
              }}
            >
              {failed[i] ? (
                <span className={styles.placeholder} aria-hidden>📦</span>
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={g.url}
                  alt={`${productName} – image ${i + 1}`}
                  loading={i === 0 ? "eager" : "lazy"}
                  decoding="async"
                  referrerPolicy="no-referrer"
                  onError={() => setFailed((f) => ({ ...f, [i]: true }))}
                />
              )}
            </button>
          ))}
        </div>

        {multi && (
          <div className={styles.dots} role="group" aria-label={t("imageGallery")}>
            {gallery.map((_, i) => (
              <button
                key={i}
                type="button"
                className={i === activeIdx ? styles.dotActive : styles.dot}
                aria-label={`${productName} – image ${i + 1}`}
                aria-current={i === activeIdx}
                onClick={() => goTo(i)}
              />
            ))}
          </div>
        )}
      </div>

      {lightboxOpen && (
        <ProductLightbox
          slides={slides}
          open={lightboxOpen}
          index={Math.min(activeIdx, gallery.length - 1)}
          onClose={() => setLightboxOpen(false)}
          onIndexChange={setActiveIdx}
        />
      )}
    </div>
  );
}
