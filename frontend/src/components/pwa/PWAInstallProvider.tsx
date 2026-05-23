"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { createContext, useCallback, useEffect, useRef, useState } from "react";
import type { BeforeInstallPromptEvent, PwaPlatform } from "@/types/pwa";
import IOSInstallSheet from "./IOSInstallSheet";
import AndroidFallbackSheet from "./AndroidFallbackSheet";

type SheetKind = null | "ios" | "fallback";

export type PwaInstallContextValue = {
  canShowEntry: boolean;
  platform: PwaPlatform;
  install: (surface: "account_shortcut" | "footer_link") => Promise<void>;
};

export const PwaInstallContext = createContext<PwaInstallContextValue | null>(null);

function logPwaEvent(name: string, props: Record<string, unknown> = {}) {
  if (typeof window === "undefined") return;
  console.info("[pwa-install]", name, props);
}

function detectPlatform(ua: string, maxTouchPoints: number): PwaPlatform {
  const isIPadOS13Plus = /Mac/.test(ua) && maxTouchPoints > 1;
  if (/iPad|iPhone|iPod/.test(ua) || isIPadOS13Plus) return "ios";
  if (/android/i.test(ua)) return "android";
  return "other";
}

export default function PWAInstallProvider({ children }: { children: React.ReactNode }) {
  const [isMobile, setIsMobile] = useState(false);
  const [isInstalled, setIsInstalled] = useState(false);
  const [platform, setPlatform] = useState<PwaPlatform>("other");
  const [sheet, setSheet] = useState<SheetKind>(null);
  const deferredPromptRef = useRef<BeforeInstallPromptEvent | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const mq = window.matchMedia("(max-width: 768px)");
    const onMqChange = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    setIsMobile(mq.matches);
    mq.addEventListener("change", onMqChange);

    const standaloneMq = window.matchMedia("(display-mode: standalone)");
    const computeInstalled = () =>
      standaloneMq.matches ||
      (window.navigator as { standalone?: boolean }).standalone === true;
    const onStandaloneChange = () => setIsInstalled(computeInstalled());
    setIsInstalled(computeInstalled());
    standaloneMq.addEventListener("change", onStandaloneChange);

    setPlatform(detectPlatform(window.navigator.userAgent, window.navigator.maxTouchPoints ?? 0));

    const onBeforeInstall = (e: Event) => {
      e.preventDefault();
      deferredPromptRef.current = e as BeforeInstallPromptEvent;
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);

    const onAppInstalled = () => {
      setIsInstalled(true);
      deferredPromptRef.current = null;
      logPwaEvent("appinstalled");
    };
    window.addEventListener("appinstalled", onAppInstalled);

    return () => {
      mq.removeEventListener("change", onMqChange);
      standaloneMq.removeEventListener("change", onStandaloneChange);
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onAppInstalled);
    };
  }, []);

  const install = useCallback<PwaInstallContextValue["install"]>(
    async (surface) => {
      logPwaEvent("entry_clicked", { surface, platform });

      if (platform === "ios") {
        logPwaEvent("ios_sheet_shown");
        setSheet("ios");
        return;
      }

      const deferred = deferredPromptRef.current;
      if (platform === "android" && deferred) {
        logPwaEvent("prompt_shown", { platform: "android" });
        try {
          await deferred.prompt();
          const choice = await deferred.userChoice;
          logPwaEvent("prompt_outcome", { outcome: choice.outcome });
        } catch (err) {
          logPwaEvent("prompt_failed", { message: (err as Error).message });
        } finally {
          deferredPromptRef.current = null;
        }
        return;
      }

      logPwaEvent("fallback_sheet_shown");
      setSheet("fallback");
    },
    [platform],
  );

  const value: PwaInstallContextValue = {
    canShowEntry: isMobile && !isInstalled,
    platform,
    install,
  };

  return (
    <PwaInstallContext.Provider value={value}>
      {children}
      {sheet === "ios" && <IOSInstallSheet onClose={() => setSheet(null)} />}
      {sheet === "fallback" && <AndroidFallbackSheet onClose={() => setSheet(null)} />}
    </PwaInstallContext.Provider>
  );
}
