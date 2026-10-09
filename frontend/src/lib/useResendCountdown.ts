// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Shared OTP-resend cooldown. Call `start()` after sending/resending a code;
 * the button stays disabled (`active`) and `secondsLeft` ticks down to 0.
 * Shared by every code-resend surface (login, invite, the seller-signup
 * wizard, PhoneVerifyModal, account deletion) so they behave identically.
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

  /** Start (or restart) the countdown. `seconds` seeds it from a server's
   * `retry_after`; omitted, it uses the hook's default. */
  const start = useCallback(
    (seconds?: number) =>
      setSecondsLeft(seconds !== undefined && seconds > 0 ? Math.ceil(seconds) : initialSeconds),
    [initialSeconds],
  );
  return { secondsLeft, start, active: secondsLeft > 0 };
}
