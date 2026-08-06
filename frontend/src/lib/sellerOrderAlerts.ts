// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { get } from "@/lib/api";
import type { SellerOrderAlertSummary } from "@/types";

export const SELLER_ORDER_SOUND_KEY = "kb_seller_order_sound";

export async function getSellerOrderAlertSummary(
  token: string
): Promise<SellerOrderAlertSummary> {
  return get<SellerOrderAlertSummary>(
    "/api/v1/orders/seller/alert-summary",
    token
  );
}

let audioCtx: AudioContext | null = null;

function getAudioContext(): AudioContext | null {
  const Ctor =
    window.AudioContext ??
    (window as unknown as { webkitAudioContext?: typeof AudioContext })
      .webkitAudioContext;
  if (!Ctor) return null;
  audioCtx = audioCtx ?? new Ctor();
  void audioCtx.resume();
  return audioCtx;
}

/**
 * Two-tone WebAudio beep. Deliberately not an <audio> element with a bundled
 * file: no binary asset in the repo, and no autoplay-policy blocking as long
 * as the context was created/resumed from the user gesture that enabled sound.
 */
export function playNewOrderChime(): void {
  try {
    const ctx = getAudioContext();
    if (!ctx) return;
    const now = ctx.currentTime;
    [880, 1174].forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, now + i * 0.18);
      gain.gain.exponentialRampToValueAtTime(0.25, now + i * 0.18 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.18 + 0.16);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now + i * 0.18);
      osc.stop(now + i * 0.18 + 0.18);
    });
  } catch {
    /* audio is a nicety — never let it break the shell */
  }
}

/** Called from the click handler that turns sound on, to unlock the context. */
export function primeAudio(): void {
  try {
    getAudioContext();
  } catch {
    /* no-op */
  }
}
