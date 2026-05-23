"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useContext } from "react";
import { PwaInstallContext, type PwaInstallContextValue } from "./PWAInstallProvider";

export function usePWAInstall(): PwaInstallContextValue {
  const ctx = useContext(PwaInstallContext);
  if (!ctx) {
    // Outside the provider (e.g., operator layout): render as if install is unavailable.
    return {
      canShowEntry: false,
      platform: "other",
      install: async () => {},
    };
  }
  return ctx;
}
