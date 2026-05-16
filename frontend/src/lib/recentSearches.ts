// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Recent-searches localStorage helper.
 * Stores up to 10 normalized terms keyed by `kb_recent_searches`.
 */

const KEY = "kb_recent_searches";
const CAP = 10;

function read(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

function write(items: string[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(items));
  } catch {
    /* private browsing or quota exceeded */
  }
}

export function list(): string[] {
  return read();
}

export function add(term: string): void {
  const t = term.trim();
  if (!t) return;
  const cur = read().filter((x) => x.toLowerCase() !== t.toLowerCase());
  cur.unshift(t);
  write(cur.slice(0, CAP));
}

export function remove(term: string): void {
  write(read().filter((x) => x.toLowerCase() !== term.toLowerCase()));
}

export function clear(): void {
  write([]);
}
