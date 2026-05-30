// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
const MIN_PER_HOUR = 60;
const MIN_PER_DAY = 60 * 24;

function pickUnit(low: number, high: number): [number, number, string, string] {
  if (low % MIN_PER_DAY === 0 && high % MIN_PER_DAY === 0) {
    return [low / MIN_PER_DAY, high / MIN_PER_DAY, "day", "days"];
  }
  if (low % MIN_PER_HOUR === 0 && high % MIN_PER_HOUR === 0) {
    return [low / MIN_PER_HOUR, high / MIN_PER_HOUR, "hour", "hours"];
  }
  return [low, high, "min", "min"];
}

/** Mirrors backend app.utils.delivery_eta.format_delivery_eta. */
export function formatDeliveryEta(minMinutes: number, maxMinutes: number): string {
  const [low, high, singular, plural] = pickUnit(minMinutes, maxMinutes);
  if (low === high) {
    return `${low} ${low === 1 ? singular : plural}`;
  }
  return `${low}–${high} ${plural}`;
}
