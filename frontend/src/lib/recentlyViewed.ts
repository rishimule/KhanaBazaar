// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
const KEY = "kb_recently_viewed";
const CAP = 20;

export interface RecentlyViewedEntry {
  product_id: number;
  store_id: number;
  name: string;
  image_url: string | null;
  viewed_at: string;
}

function readSafe(): RecentlyViewedEntry[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const arr: unknown = JSON.parse(raw);
    if (!Array.isArray(arr)) return [];
    return arr.filter(
      (e): e is RecentlyViewedEntry =>
        typeof e === "object" &&
        e !== null &&
        typeof (e as RecentlyViewedEntry).product_id === "number" &&
        typeof (e as RecentlyViewedEntry).store_id === "number" &&
        typeof (e as RecentlyViewedEntry).name === "string",
    ).slice(0, CAP);
  } catch {
    localStorage.removeItem(KEY);
    return [];
  }
}

export function getRecentlyViewed(): RecentlyViewedEntry[] {
  if (typeof window === "undefined") return [];
  return readSafe();
}

export function pushRecentlyViewed(
  entry: Omit<RecentlyViewedEntry, "viewed_at">,
): void {
  if (typeof window === "undefined") return;
  const existing = readSafe().filter((e) => e.product_id !== entry.product_id);
  const next: RecentlyViewedEntry[] = [
    { ...entry, viewed_at: new Date().toISOString() },
    ...existing,
  ].slice(0, CAP);
  localStorage.setItem(KEY, JSON.stringify(next));
}
