"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/AuthContext";
import { usePWAInstall } from "@/components/pwa/usePWAInstall";
import {
  hasActiveSubscription,
  pushSupported,
  subscribeToPush,
  unsubscribeFromPush,
} from "@/lib/push";
import { subscribePush, unsubscribePush } from "@/lib/notifications";

export type PushOptInState =
  | "loading"
  | "unsupported"
  | "needs_install_ios"
  | "default"
  | "enabled"
  | "denied";

export function usePushOptIn(): {
  state: PushOptInState;
  enable: () => Promise<void>;
  disable: () => Promise<void>;
  openInstall: () => void;
} {
  const { token } = useAuth();
  const { platform, install } = usePWAInstall();
  const [state, setState] = useState<PushOptInState>("loading");

  const compute = useCallback(async (): Promise<PushOptInState> => {
    // pushSupported() is false in an un-installed iOS Safari tab (no
    // Notification/PushManager) but true inside an installed iOS PWA (16.4+),
    // so `platform === "ios" && !pushSupported()` reliably means "needs install".
    if (!pushSupported()) {
      return platform === "ios" ? "needs_install_ios" : "unsupported";
    }
    if (typeof Notification !== "undefined" && Notification.permission === "denied") {
      return "denied";
    }
    if (await hasActiveSubscription()) return "enabled";
    return "default";
  }, [platform]);

  useEffect(() => {
    let active = true;
    compute().then((s) => {
      if (active) setState(s);
    });
    return () => {
      active = false;
    };
  }, [compute]);

  const enable = useCallback(async () => {
    if (!token) return;
    try {
      const payload = await subscribeToPush(); // fires the native prompt
      if (!payload) {
        setState(await compute()); // denied / unsupported
        return;
      }
      await subscribePush(token, payload);
      setState("enabled");
    } catch {
      setState(await compute());
    }
  }, [token, compute]);

  const disable = useCallback(async () => {
    if (!token) return;
    try {
      const endpoint = await unsubscribeFromPush();
      if (endpoint) await unsubscribePush(token, endpoint);
    } catch {
      /* best-effort */
    } finally {
      setState("default");
    }
  }, [token]);

  const openInstall = useCallback(() => {
    void install("notifications");
  }, [install]);

  return { state, enable, disable, openInstall };
}
