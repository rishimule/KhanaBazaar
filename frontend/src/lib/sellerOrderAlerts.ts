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
  // A context can end up `closed` (iOS backgrounding, bfcache restore). Reusing
  // the dead singleton would silently kill sound for the rest of the session.
  if (audioCtx === null || audioCtx.state === "closed") {
    audioCtx = new Ctor();
  }
  return audioCtx;
}

/** Schedule the two tones. Assumes the context is already running. */
function scheduleTones(ctx: AudioContext): void {
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
    // Without this the gain node stays wired to destination for the life of
    // the page, once per chime.
    osc.onended = () => {
      try {
        osc.disconnect();
        gain.disconnect();
      } catch {
        /* already torn down */
      }
    };
    osc.start(now + i * 0.18);
    osc.stop(now + i * 0.18 + 0.18);
  });
}

/**
 * Two-tone WebAudio beep. Deliberately not an <audio> element with a bundled
 * file: no binary asset in the repo.
 *
 * A context that is still `suspended` (the seller enabled sound in an earlier
 * session, so this page load has had no user gesture) has a frozen clock —
 * scheduling against it would queue every tone to fire at once the moment the
 * seller next taps anything. So resume FIRST and only schedule once running.
 */
export function playNewOrderChime(): void {
  try {
    const ctx = getAudioContext();
    if (!ctx) return;
    if (ctx.state === "running") {
      scheduleTones(ctx);
      return;
    }
    ctx
      .resume()
      .then(() => {
        if (ctx.state === "running") scheduleTones(ctx);
      })
      .catch(() => {
        /* still blocked by the autoplay policy — stay silent, don't queue */
      });
  } catch {
    /* audio is a nicety — never let it break the shell */
  }
}

/** Called from the click handler that turns sound on, to unlock the context. */
export function primeAudio(): void {
  try {
    const ctx = getAudioContext();
    if (ctx) ctx.resume().catch(() => {});
  } catch {
    /* no-op */
  }
}
