// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Shared OTP-resend cooldown. Call `start()` after sending/resending a code;
 * the button stays disabled (`active`) and `secondsLeft` ticks down to 0.
 * Used by login, the seller-signup wizard, and PhoneVerifyModal so all three
 * surfaces behave identically.
 */
export function useResendCountdown(initialSeconds = 60) {
  const [secondsLeft, setSecondsLeft] = useState(0);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    if (secondsLeft <= 0) {
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return;
    }
    if (timerRef.current) return;
    timerRef.current = window.setInterval(() => {
      setSecondsLeft((s) => (s <= 1 ? 0 : s - 1));
    }, 1000);
    return () => {
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [secondsLeft]);

  const start = useCallback(() => setSecondsLeft(initialSeconds), [initialSeconds]);
  return { secondsLeft, start, active: secondsLeft > 0 };
}
