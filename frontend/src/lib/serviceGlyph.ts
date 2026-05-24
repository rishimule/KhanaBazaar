// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

// Emoji glyph per service, keyed by the slugs seeded in `_dev_seed_data.py`.
const SERVICE_GLYPH: Record<string, string> = {
  grocery: "🛒",
  electronics: "🔌",
  pharmacy: "💊",
  food: "🍱",
  bakery: "🍞",
  "meat-seafood": "🥩",
  beauty: "💄",
  stationery: "📚",
  "pet-supplies": "🐾",
  "home-kitchen": "🏠",
  "flowers-plants": "🌸",
  "sports-fitness": "🏋️",
};

export function serviceGlyph(slug: string): string {
  const k = slug.toLowerCase();
  if (SERVICE_GLYPH[k]) return SERVICE_GLYPH[k];
  for (const key in SERVICE_GLYPH) {
    if (k.includes(key)) return SERVICE_GLYPH[key];
  }
  return "🛍️";
}
