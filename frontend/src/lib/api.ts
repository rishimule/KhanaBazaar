// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
/**
 * Khana Bazaar — API Client
 *
 * A thin, typed fetch wrapper configured to talk to the FastAPI backend.
 * Reads the base URL from NEXT_PUBLIC_API_URL env var.
 * Supports optional auth token for protected endpoints.
 *
 * Attaches Accept-Language on every request from the active locale (next-intl
 * on the server; the URL prefix / locale cookies in the browser — see
 * resolveLocale). Backend uses this to localize catalog/store responses.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
// Server-side fetches (RSC, route handlers) can't use Next.js rewrites — they
// need an absolute URL. INTERNAL_API_URL is the in-cluster/in-host backend URL
// used only on the server. Falls back to NEXT_PUBLIC_API_URL when that is
// already absolute, otherwise localhost:8000 for local dev.
const INTERNAL_API_BASE =
  process.env.INTERNAL_API_URL ||
  (process.env.NEXT_PUBLIC_API_URL && process.env.NEXT_PUBLIC_API_URL.startsWith("http")
    ? process.env.NEXT_PUBLIC_API_URL
    : "http://localhost:8000");
import {
  CUSTOMER_LOCALE_COOKIE,
  CUSTOMER_LOCALE_PREFIX_RE,
  DEFAULT_LOCALE,
  OPERATOR_LOCALE_COOKIE,
  OPERATOR_PATH_RE,
  SUPPORTED_LOCALES,
} from "@/lib/localeCookies";

function readBrowserCookie(name: string): string | null {
  const m = document.cookie.match(
    new RegExp(`(?:^|;\\s*)${name}=([^;]+)`),
  );
  const value = m?.[1];
  return value && SUPPORTED_LOCALES.has(value) ? value : null;
}

/** Standard error thrown when a FastAPI backend response is not ok. */
export class ApiError extends Error {
  detail: string;
  status: number;
  constructor(detail: string, status: number) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
    this.name = "ApiError";
    this.detail = detail;
    this.status = status;
  }
}

/** Throws a structured error when the response is not ok. */
async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.detail ?? res.statusText, res.status);
  }
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

/** Resolve the current locale for outbound API requests so the backend
 * localizes catalog/store responses to match what's on screen.
 *
 * - Server (RSC, route handlers): next-intl's getLocale() (URL-derived on
 *   customer routes); fall back to the NEXT_LOCALE cookie; finally
 *   DEFAULT_LOCALE. Operator server components are not covered here — every
 *   operator page fetches client-side, and the browser branch below handles
 *   the KB_OP_LOCALE cookie. A future server-rendered operator page doing a
 *   localized fetch would need the operator cookie threaded in here.
 * - Browser: the active locale is authoritative from the URL prefix on customer
 *   routes (matches next-intl's `useLocale()`), from KB_OP_LOCALE on operator
 *   routes; the NEXT_LOCALE cookie and DEFAULT_LOCALE are fallbacks. Reading the
 *   URL prefix (not just the cookie) keeps catalog language aligned with the
 *   page even for a guest deep-linking to `/hi/...` before any cookie is set.
 */
async function resolveLocale(): Promise<string> {
  if (typeof window === "undefined") {
    try {
      const mod = await import("next-intl/server");
      const locale = await mod.getLocale();
      if (typeof locale === "string" && SUPPORTED_LOCALES.has(locale)) return locale;
    } catch {
      /* fall through to cookie */
    }
    try {
      const { cookies } = await import("next/headers");
      const c = (await cookies()).get(CUSTOMER_LOCALE_COOKIE)?.value;
      if (c && SUPPORTED_LOCALES.has(c)) return c;
    } catch {
      /* not in a request context */
    }
    return DEFAULT_LOCALE;
  }
  const path = window.location.pathname;
  // Operator routes: the dashboard's own cookie (fall back to the storefront
  // cookie), so catalog/product names match the dashboard language.
  if (OPERATOR_PATH_RE.test(path)) {
    return (
      readBrowserCookie(OPERATOR_LOCALE_COOKIE) ??
      readBrowserCookie(CUSTOMER_LOCALE_COOKIE) ??
      DEFAULT_LOCALE
    );
  }
  // Customer routes: the URL locale prefix is authoritative (en is unprefixed,
  // and locale detection is off, so an unprefixed path is definitively the
  // default locale — never fall back to a possibly-stale cookie here).
  const prefix = path.match(CUSTOMER_LOCALE_PREFIX_RE);
  return prefix ? prefix[1] : DEFAULT_LOCALE;
}

/** Build a full URL and merge default headers. Optionally attach auth token. */
async function buildRequest(
  path: string,
  options: RequestInit = {},
  token?: string | null
): Promise<[string, RequestInit]> {
  const base = typeof window === "undefined" ? INTERNAL_API_BASE : API_BASE;
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  const locale = await resolveLocale();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "Accept-Language": locale,
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return [url, { ...options, headers }];
}

/** GET request */
export async function get<T>(
  path: string,
  token?: string | null,
  options?: RequestInit
): Promise<T> {
  const [url, init] = await buildRequest(path, { ...options, method: "GET" }, token);
  const res = await fetch(url, init);
  return handleResponse<T>(res);
}

/** POST request */
export async function post<T>(
  path: string,
  body?: unknown,
  token?: string | null,
  options?: RequestInit
): Promise<T> {
  const [url, init] = await buildRequest(
    path,
    {
      ...options,
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    },
    token
  );
  const res = await fetch(url, init);
  return handleResponse<T>(res);
}

/** PUT request */
export async function put<T>(
  path: string,
  body?: unknown,
  token?: string | null,
  options?: RequestInit
): Promise<T> {
  const [url, init] = await buildRequest(
    path,
    {
      ...options,
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    },
    token
  );
  const res = await fetch(url, init);
  return handleResponse<T>(res);
}

/** PATCH request */
export async function patch<T>(
  path: string,
  body?: unknown,
  token?: string | null,
  options?: RequestInit
): Promise<T> {
  const [url, init] = await buildRequest(
    path,
    {
      ...options,
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    },
    token
  );
  const res = await fetch(url, init);
  return handleResponse<T>(res);
}

/** DELETE request */
export async function del<T>(
  path: string,
  token?: string | null,
  options?: RequestInit
): Promise<T> {
  const [url, init] = await buildRequest(
    path,
    { ...options, method: "DELETE" },
    token
  );
  const res = await fetch(url, init);
  return handleResponse<T>(res);
}
