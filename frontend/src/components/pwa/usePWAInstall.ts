"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useContext } from "react";
import { PwaInstallContext } from "./PWAInstallProvider";

export function usePWAInstall() {
  const ctx = useContext(PwaInstallContext);
  if (!ctx) {
    // Outside the provider (e.g., operator layout): render as if install is unavailable.
    return {
      canShowEntry: false as const,
      platform: "other" as const,
      install: async () => {},
    };
  }
  return ctx;
}
