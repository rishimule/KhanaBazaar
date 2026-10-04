"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Server switches a client must know about before it renders.
 *
 * Advisory only: every switch here is still enforced server-side on the
 * request that acts on it. `phoneOtpEnabled` exists purely so the phone
 * screens don't promise a code that will never be sent — the OTP endpoints'
 * own `otp_required` response field stays the authority on what happened.
 */
import { useEffect, useState } from "react";
import { get } from "@/lib/api";

interface PublicConfig {
  phone_otp_enabled: boolean;
  /** COURIER_MAX_RADIUS_KM / COURIER_STALE_DAYS (absent on older APIs). */
  courier_max_radius_km?: number;
  courier_stale_days?: number;
}

let cached: Promise<PublicConfig> | null = null;

export function getPublicConfig(): Promise<PublicConfig> {
  if (cached) return cached;
  cached = get<PublicConfig>("/api/v1/meta/public-config").catch((err) => {
    cached = null;
    throw err;
  });
  return cached;
}

export interface CourierLimits {
  maxRadiusKm: number | null;
  staleDays: number | null;
}

/**
 * The courier limits, so operator screens follow the env instead of
 * hard-coding its defaults. `null` until loaded (or on an older API): callers
 * then drop the number from their copy and leave the check to the server.
 */
export function useCourierLimits(): CourierLimits {
  const [limits, setLimits] = useState<CourierLimits>({ maxRadiusKm: null, staleDays: null });
  useEffect(() => {
    let live = true;
    getPublicConfig()
      .then((c) => {
        if (live) {
          setLimits({
            maxRadiusKm: c.courier_max_radius_km ?? null,
            staleDays: c.courier_stale_days ?? null,
          });
        }
      })
      .catch(() => {
        /* keep the unknowns */
      });
    return () => {
      live = false;
    };
  }, []);
  return limits;
}

/**
 * `true` until proven otherwise: an unreachable config endpoint must not
 * silently relabel the UI as if verification were off.
 */
export function usePhoneOtpEnabled(): boolean {
  const [enabled, setEnabled] = useState(true);
  useEffect(() => {
    let live = true;
    getPublicConfig()
      .then((c) => {
        if (live) setEnabled(c.phone_otp_enabled);
      })
      .catch(() => {
        /* keep the safe default */
      });
    return () => {
      live = false;
    };
  }, []);
  return enabled;
}
