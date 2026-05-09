// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { get } from "@/lib/api";

let cached: Promise<string[]> | null = null;

export function getIndianStates(): Promise<string[]> {
  if (cached) return cached;
  cached = get<{ states: string[] }>("/api/v1/meta/indian-states")
    .then((r) => r.states)
    .catch((err) => {
      cached = null;
      throw err;
    });
  return cached;
}
