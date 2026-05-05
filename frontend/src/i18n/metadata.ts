import { routing } from "./routing";

export function alternateLanguages(pathname: string): Record<string, string> {
  const map: Record<string, string> = {};
  for (const locale of routing.locales) {
    map[locale] = locale === routing.defaultLocale ? pathname : `/${locale}${pathname}`;
  }
  map["x-default"] = pathname;
  return map;
}
