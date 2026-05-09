// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { routing } from "./routing";

export function alternateLanguages(pathname: string): Record<string, string> {
  const map: Record<string, string> = {};
  for (const locale of routing.locales) {
    map[locale] = locale === routing.defaultLocale ? pathname : `/${locale}${pathname}`;
  }
  map["x-default"] = pathname;
  return map;
}
