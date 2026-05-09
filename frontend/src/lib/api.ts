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
 * on the server, NEXT_LOCALE cookie in the browser). Backend uses this to
 * localize catalog/store responses.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SUPPORTED_LOCALES = new Set(["en", "hi", "mr", "gu", "pa"]);
const DEFAULT_LOCALE = "en";
const COOKIE_NAME = "NEXT_LOCALE";

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

/** Resolve the current locale for outbound API requests.
 *
 * - Server (RSC, route handlers): try next-intl's getLocale(); fall back to
 *   NEXT_LOCALE cookie; finally DEFAULT_LOCALE.
 * - Browser: read NEXT_LOCALE cookie; fall back to DEFAULT_LOCALE.
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
      const c = (await cookies()).get(COOKIE_NAME)?.value;
      if (c && SUPPORTED_LOCALES.has(c)) return c;
    } catch {
      /* not in a request context */
    }
    return DEFAULT_LOCALE;
  }
  const m = document.cookie.match(/(?:^|;\s*)NEXT_LOCALE=([^;]+)/);
  const c = m?.[1];
  return c && SUPPORTED_LOCALES.has(c) ? c : DEFAULT_LOCALE;
}

/** Build a full URL and merge default headers. Optionally attach auth token. */
async function buildRequest(
  path: string,
  options: RequestInit = {},
  token?: string | null
): Promise<[string, RequestInit]> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
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
