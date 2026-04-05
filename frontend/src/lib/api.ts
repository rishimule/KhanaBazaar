/**
 * Khana Bazaar — API Client
 *
 * A thin, typed fetch wrapper configured to talk to the FastAPI backend.
 * Reads the base URL from NEXT_PUBLIC_API_URL env var.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Standard error shape returned by our FastAPI backend. */
export interface ApiError {
  detail: string;
  status: number;
}

/** Throws a structured error when the response is not ok. */
async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const error: ApiError = {
      detail: body.detail ?? res.statusText,
      status: res.status,
    };
    throw error;
  }
  return res.json() as Promise<T>;
}

/** Build a full URL and merge default headers. */
function buildRequest(
  path: string,
  options: RequestInit = {}
): [string, RequestInit] {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...options.headers,
  };
  return [url, { ...options, headers }];
}

/** GET request */
export async function get<T>(path: string, options?: RequestInit): Promise<T> {
  const [url, init] = buildRequest(path, { ...options, method: "GET" });
  const res = await fetch(url, init);
  return handleResponse<T>(res);
}

/** POST request */
export async function post<T>(
  path: string,
  body?: unknown,
  options?: RequestInit
): Promise<T> {
  const [url, init] = buildRequest(path, {
    ...options,
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
  const res = await fetch(url, init);
  return handleResponse<T>(res);
}

/** PUT request */
export async function put<T>(
  path: string,
  body?: unknown,
  options?: RequestInit
): Promise<T> {
  const [url, init] = buildRequest(path, {
    ...options,
    method: "PUT",
    body: body ? JSON.stringify(body) : undefined,
  });
  const res = await fetch(url, init);
  return handleResponse<T>(res);
}

/** DELETE request */
export async function del<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const [url, init] = buildRequest(path, { ...options, method: "DELETE" });
  const res = await fetch(url, init);
  return handleResponse<T>(res);
}
