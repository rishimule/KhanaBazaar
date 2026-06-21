// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
// Mirrors backend app.utils.delivery_window — keep keys + hour labels in sync.

export type DeliveryWindowKey = "morning" | "afternoon" | "evening";

export const WINDOW_ORDER: DeliveryWindowKey[] = ["morning", "afternoon", "evening"];

export const WINDOW_META: Record<
  DeliveryWindowKey,
  { startHour: number; endHour: number; hours: string }
> = {
  morning: { startHour: 7, endHour: 11, hours: "7–11 AM" },
  afternoon: { startHour: 11, endHour: 15, hours: "11 AM – 3 PM" },
  evening: { startHour: 15, endHour: 21, hours: "3–9 PM" },
};

const HORIZON_DAYS = 6; // today + 6 days

function toIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export interface SelectableDay {
  date: string; // YYYY-MM-DD
  relative: "today" | "tomorrow" | null;
  windows: DeliveryWindowKey[];
}

/**
 * The selectable days (today + 6) with each day's still-offerable windows.
 * On today, a window whose end-hour has already passed is dropped. A day with
 * no remaining windows (late today) is omitted.
 *
 * Note: this trusts the browser's local clock as an IST proxy (the app targets
 * India). The backend validates the chosen date against IST [today, today+6];
 * a user whose browser TZ differs from IST near midnight could be offered a
 * boundary date the backend then rejects with 422. Acceptable for a soft hint.
 */
export function buildSelectableOptions(now: Date = new Date()): SelectableDay[] {
  const days: SelectableDay[] = [];
  for (let i = 0; i <= HORIZON_DAYS; i++) {
    const d = new Date(now);
    d.setDate(now.getDate() + i);
    const isToday = i === 0;
    const windows = WINDOW_ORDER.filter(
      (w) => !isToday || WINDOW_META[w].endHour > now.getHours(),
    );
    if (windows.length === 0) continue;
    days.push({
      date: toIsoDate(d),
      relative: i === 0 ? "today" : i === 1 ? "tomorrow" : null,
      windows,
    });
  }
  return days;
}

/** Absolute date label, e.g. "Sat, 21 Jun" (locale-aware). */
export function formatDateLabel(dateIso: string, locale: string): string {
  // Parse as local date (append T00:00 to avoid UTC shift).
  const d = new Date(`${dateIso}T00:00:00`);
  return new Intl.DateTimeFormat(locale, {
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(d);
}

export function isDeliveryWindowKey(v: unknown): v is DeliveryWindowKey {
  return v === "morning" || v === "afternoon" || v === "evening";
}
