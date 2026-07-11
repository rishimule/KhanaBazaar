"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { QRCodeCanvas, QRCodeSVG } from "qrcode.react";
import styles from "./StoreQRCard.module.css";

interface StoreQRCardProps {
  storeId: number;
  storeName: string;
}

export default function StoreQRCard({ storeId, storeName }: StoreQRCardProps) {
  const t = useTranslations("StoreQR");
  const [mounted, setMounted] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time client-mount gate (window access)
    setMounted(true);
  }, []);

  // `window` is only available on the client; hold rendering the QR until mount.
  const url = mounted ? `${window.location.origin}/stores/${storeId}` : "";

  function downloadPng() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const a = document.createElement("a");
    a.href = canvas.toDataURL("image/png");
    a.download = `store-${storeId}-qr.png`;
    a.click();
  }

  function downloadSvg() {
    const svg = svgRef.current;
    if (!svg) return;
    let data = new XMLSerializer().serializeToString(svg);
    if (!data.includes("xmlns")) {
      data = data.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');
    }
    const blob = new Blob([data], { type: "image/svg+xml;charset=utf-8" });
    const href = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = href;
    a.download = `store-${storeId}-qr.svg`;
    a.click();
    URL.revokeObjectURL(href);
  }

  function printPoster() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const png = canvas.toDataURL("image/png");

    // Print via a hidden same-document iframe rather than window.open: no popup
    // blocker to trip over, and the QR paints inside the isolated document
    // before we call print() (a cross-window open + immediate print() prints a
    // blank page on WebKit/Safari). Build the DOM with createElement +
    // textContent (no document.write / innerHTML) so a seller-controlled store
    // name can never inject markup.
    document.getElementById("kb-print-frame")?.remove();
    const iframe = document.createElement("iframe");
    iframe.id = "kb-print-frame";
    iframe.setAttribute("aria-hidden", "true");
    iframe.style.cssText =
      "position:fixed;right:0;bottom:0;width:0;height:0;border:0;";
    document.body.appendChild(iframe);

    const frame = iframe.contentWindow;
    const doc = frame?.document;
    if (!frame || !doc) {
      iframe.remove();
      return;
    }

    doc.title = storeName;
    const style = doc.createElement("style");
    style.textContent =
      "body{font-family:system-ui,-apple-system,sans-serif;display:flex;" +
      "flex-direction:column;align-items:center;justify-content:center;" +
      "gap:16px;padding:32px;text-align:center}" +
      "h1{font-size:26px;margin:0;color:#07101A;overflow-wrap:anywhere}" +
      "p{font-size:18px;color:#0F6B06;font-weight:600;margin:0;overflow-wrap:anywhere}" +
      "img{width:320px;height:320px}";
    doc.head.appendChild(style);

    const h1 = doc.createElement("h1");
    h1.textContent = storeName;
    const cta = doc.createElement("p");
    cta.textContent = t("posterCta");
    const img = doc.createElement("img");
    img.alt = "";
    img.onload = () => {
      frame.focus();
      // Let layout/paint flush before printing, then tear the frame down only
      // after the print dialog closes (never on a timer — that would cancel a
      // still-open dialog on non-blocking browsers).
      setTimeout(() => {
        frame.onafterprint = () => iframe.remove();
        frame.print();
      }, 100);
    };
    img.src = png;
    doc.body.append(h1, cta, img);
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.poster}>
        <h2 className={styles.storeName}>{storeName}</h2>
        <p className={styles.cta}>{t("posterCta")}</p>
        <div className={styles.qrBox}>
          {mounted && (
            <>
              <QRCodeSVG ref={svgRef} value={url} size={256} level="M" />
              <QRCodeCanvas
                ref={canvasRef}
                value={url}
                size={1024}
                level="M"
                style={{ display: "none" }}
              />
            </>
          )}
        </div>
        <p className={styles.hint}>{t("posterHint")}</p>
      </div>
      <div className={styles.actions}>
        <button className="btn btn-primary" onClick={printPoster} disabled={!mounted}>
          {t("print")}
        </button>
        <button className="btn btn-outline" onClick={downloadPng} disabled={!mounted}>
          {t("downloadPng")}
        </button>
        <button className="btn btn-outline" onClick={downloadSvg} disabled={!mounted}>
          {t("downloadSvg")}
        </button>
      </div>
    </div>
  );
}
